import base64
import copy
import os
import random
import string
from datetime import datetime
from enum import Enum
from typing import Any, Callable, List, Optional, Tuple

import libvirt
import oci
import waiting

from assisted_test_infra.test_infra import BaseClusterConfig
from assisted_test_infra.test_infra.controllers.node_controllers.disk import Disk
from assisted_test_infra.test_infra.controllers.node_controllers.node import Node
from assisted_test_infra.test_infra.controllers.node_controllers.node_controller import NodeController
from assisted_test_infra.test_infra.helper_classes.config import BaseNodesConfig
from assisted_test_infra.test_infra.helper_classes.config.base_oci_config import BaseOciConfig
from service_client import log


def random_name(prefix="", length=8):
    return prefix + "".join(random.choice(string.ascii_letters) for i in range(length))


class OciState(Enum):
    RUNNING = "RUNNING"
    STARTING = "STARTING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    TERMINATING = "TERMINATING"
    TERMINATED = "TERMINATED"
    RESETTING = "RESETTING"
    RESTARTING = "RESTARTING"
    ACTIVE = "ACTIVE"
    SUCCEEDED = "SUCCEEDED"
    CREATED = "CREATED"
    IN_PROGRESS: "IN_PROGRESS"
    FAILED = "FAILED"
    CANCELING = "CANCELING"
    CANCELED = "CANCELED"


class CleanupResource:
    """Store resource to be destroyed / deleted.

    The cleanup resource called on teardown and stored in a stack of actions.
    """

    def __init__(self, callback: Callable, *args, **kwargs):
        self.callback = callback
        self.args = args
        self.kwargs = kwargs

    def __call__(self):
        log.info(f"Cleaning up resource: {self.callback}({self.args}, {self.kwargs})")
        try:
            self.callback(*self.args, **self.kwargs)
        except Exception as e:
            log.info(f"Cleaning up resource fails: {self.callback}({self.args}, {self.kwargs} {e})")


class OciApiController(NodeController):
    """Install openshift cluster with oracle nodes using OCI API code.

    It decouples the terraform implementation from the code, used terraform as blackbox provided by oracle.
    They create terraform templates for customer, we run them as is.
    Run oci cluster installation as customer, handle resource creation and deletion.

    Steps:
    1. Create a bucket (object-storage)
    2. Upload ISO file to the object-storage bucket
    3. Create pre authenticated - return ISO download link from OCI storage
    4. Create a stack , declare the provision configuration.
    5. Upload infrastructure zip file to the stack and set terraform variable
    6. Start running job creating oci nodes discovered by redhat cluster and return terraform output files
    7. Once nodes are discovered we configure manifest return in #6
    """

    _config: BaseOciConfig
    # cleanup list , runs on teardown in LIFO cleanup
    _cleanup_resources = []

    def __init__(self, config: BaseNodesConfig, cluster_config: BaseClusterConfig):
        super().__init__(config, cluster_config)
        self._cloud_provider = None
        self._oci_compartment_oicd = self._config.oci_compartment_oicd
        self._initialize_oci_clients()

    @property
    def cloud_provider(self):
        # Called from test_cases , modify manifests
        return self._cloud_provider

    @cloud_provider.setter
    def cloud_provider(self, cloud_provider):
        self._cloud_provider = cloud_provider

    def _initialize_oci_clients(self):
        """Initialize oci clients.

        Added compute , volume for future usage
        """
        try:
            oci_config = self._config.get_provider_config()
            oci.config.validate_config(oci_config)
            log.info("Initialize oci clients")
            self._object_storage_client = oci.object_storage.ObjectStorageClient(self._config.get_provider_config())
            self._compute_client = oci.core.ComputeClient(self._config.get_provider_config())
            self._volume_client = oci.core.BlockstorageClient(self._config.get_provider_config())
            # resource manager for stack creation and job
            self._resource_manager_client = oci.resource_manager.ResourceManagerClient(
                self._config.get_provider_config()
            )
            # wrapper for _resource_manager_client with waiters
            self._resource_manager_client_composite_operations = (
                oci.resource_manager.ResourceManagerClientCompositeOperations(self._resource_manager_client)
            )
        except Exception as e:
            raise e

    def _create_bucket(
        self,
        name: str,
        public_access_type: str = "NoPublicAccess",
        storage_tier: str = "Standard",
        object_events_enabled: bool = False,
        versioning: str = "Disabled",
        auto_tiering: str = "Disabled",
        **kwargs,
    ) -> str:
        bucket_details = {
            "name": name,
            "compartment_id": self._oci_compartment_oicd,
            "public_access_type": public_access_type,
            "storage_tier": storage_tier,
            "object_events_enabled": object_events_enabled,
            "versioning": versioning,
            "auto_tiering": auto_tiering,
            **kwargs,
        }
        create_bucket_details = oci.object_storage.models.CreateBucketDetails(**bucket_details)
        namespace = self._object_storage_client.get_namespace().data

        log.info(f"Create oci bucket {create_bucket_details}")
        obj = self._object_storage_client.create_bucket(namespace, create_bucket_details)
        self._cleanup_resources.append(CleanupResource(self._object_storage_client.delete_bucket, namespace, name))
        assert obj.status == 200
        # Need the namespace and bucket name
        return namespace

    def _upload_iso_to_bucket(self, file_path: str, namespace: str, bucket_name: str) -> None:
        log.info(f"Upload iso file to bucket object storage {file_path}")
        if os.path.isfile(file_path):
            try:
                self._object_storage_client.put_object(
                    namespace, bucket_name, os.path.basename(file_path), open(file_path, "rb")
                )
                self._cleanup_resources.append(
                    CleanupResource(
                        self._object_storage_client.delete_object, namespace, bucket_name, os.path.basename(file_path)
                    )
                )
            except Exception as e:
                raise e
        else:
            raise RuntimeError(f"Could not find {file_path}")

    def _create_pre_authenticated(
        self, name: str, file_path: str, namespace: str, bucket_name: str, access_type: str = "ObjectRead"
    ) -> str:
        pre_authenticated = {
            "name": name,
            "object_name": os.path.basename(file_path),
            "access_type": access_type,
            "time_expires": datetime.strptime("2030-07-16T17:46:56.731Z", "%Y-%m-%dT%H:%M:%S.%fZ"),
        }
        log.info(f"Create pre-authenticated secured url path for iso file {pre_authenticated}")
        pre_authenticated_req = oci.object_storage.models.CreatePreauthenticatedRequestDetails(**pre_authenticated)
        obj = self._object_storage_client.create_preauthenticated_request(
            namespace_name=namespace,
            bucket_name=bucket_name,
            create_preauthenticated_request_details=pre_authenticated_req,
        )
        self._cleanup_resources.append(
            CleanupResource(
                self._object_storage_client.delete_preauthenticated_request, namespace, bucket_name, obj.data.id
            )
        )

        assert obj.status == 200
        return obj.data.full_path

    def _terraform_variables(
        self,
        cluster_name: str,
        image_source_uri: str,
        control_plane_shape: str,
        compute_shape: str,
        compute_count: str,
        base_dns: str,
        **kwargs,
    ) -> dict[str, str]:
        """Terraform variables before running the stack job.

        All variables configured in variables.tf file.
        Allow to extend variables based on terraform
        Must use same cluster name and base domain -qeXXXX.oci-rhelcert.edge-sro.rhecoeng.com
        BM.Standard3.64 shape refers to boot from iscsi network
        VM.Standard3.64 shape refers to boot from local
        """
        variables = {
            "compartment_ocid": self._oci_compartment_oicd,
            "region": self._config.get_provider_config()["region"],
            "tenancy_ocid": self._config.get_provider_config()["tenancy"],
            "cluster_name": str(cluster_name),
            "openshift_image_source_uri": image_source_uri,
            "control_plane_shape": control_plane_shape,
            "compute_shape": compute_shape,
            "compute_count": compute_count,
            "zone_dns": base_dns,
            **kwargs,
        }
        log.info(f"Terraform variables before apply setting  {variables}")
        return variables

    @staticmethod
    def _base64_zip_file(file_zip: str) -> str:
        """Encode terraform zip file as base64 string."""
        if not os.path.isfile(file_zip):
            raise RuntimeError(f"Could not find {file_zip}")

        with open(file_zip, mode="rb") as f:
            bytes_data = f.read()
            encoded = base64.b64encode(bytes_data).decode("utf-8")
        return encoded

    def _create_stack(
        self,
        name: str,
        namespace: str,
        bucket_name: str,
        terraform_zip_path: str,
        terraform_variable: dict,
        timeout_seconds: int = 1200,
    ) -> str:

        template_config = {
            "config_source_type": "ZIP_UPLOAD",
            "zip_file_base64_encoded": self._base64_zip_file(terraform_zip_path),
            "working_directory": "infrastructure",
        }

        template_config_create = oci.resource_manager.models.CreateZipUploadConfigSourceDetails(**template_config)

        custom_terraform_provider = {
            "region": self._config.get_provider_config()["region"],
            "namespace": namespace,
            "bucket_name": bucket_name,
        }
        custom_terraform_provider_config = oci.resource_manager.models.CustomTerraformProvider(
            **custom_terraform_provider
        )
        log.info(f"Create oci stack  {custom_terraform_provider}")
        stack_details = {
            "compartment_id": self._oci_compartment_oicd,
            "display_name": name,
            "description": name,
            "config_source": template_config_create,
            "custom_terraform_provider": custom_terraform_provider_config,
            "variables": terraform_variable,
        }
        create_stack_details = oci.resource_manager.models.CreateStackDetails(**stack_details)
        try:
            obj = self._resource_manager_client_composite_operations.create_stack_and_wait_for_state(
                create_stack_details,
                wait_for_states=[OciState.ACTIVE.value],
                waiter_kwargs={"max_wait_seconds": timeout_seconds, "succeed_on_not_found": False},
            )
            self._cleanup_resources.append(
                CleanupResource(
                    self._resource_manager_client_composite_operations.delete_stack_and_wait_for_state, obj.data.id
                )
            )
        except Exception as e:
            log.info(f"failed to create stack {e}")
            raise
        return obj.data.id

    def _apply_job_from_stack(
        self, stack_id: str, display_name: str, timeout_seconds: int = 1800, interval_wait: int = 60
    ) -> str:
        """Apply job will run the stack terraform code and create the resources.

        On failure - raise Exception and cleanup resources
        On success - return output , a list with contents. cleanup on teardown
        [{output_name: "oci_ccm_config", output_value: string_value},
         {output_name: "open_shift_api_apps_lb_addr", output_value: string_value},
         {output_name: "open_shift_api_int_lb_addr", output_value: string_value}]
        """

        job_info = {
            "stack_id": stack_id,
            "display_name": display_name,
            "operation": "APPLY",
            "apply_job_plan_resolution": oci.resource_manager.models.ApplyJobPlanResolution(
                is_use_latest_job_id=False, is_auto_approved=True
            ),
        }

        log.info(f"Apply job configuration {job_info}")
        create_job_details = oci.resource_manager.models.CreateJobDetails(**job_info)
        # create a destroy job
        destroy_job_details = copy.deepcopy(create_job_details)
        destroy_job_details.operation = "DESTROY"
        try:
            # Destroy the job when success or failed - remove all created resources - Waiting in cleanup
            self._cleanup_resources.append(
                CleanupResource(
                    self._resource_manager_client_composite_operations.create_job_and_wait_for_state,
                    destroy_job_details,
                    wait_for_states=[OciState.SUCCEEDED.value],
                    waiter_kwargs={"max_wait_seconds": timeout_seconds, "succeed_on_not_found": False},
                )
            )

            job = self._resource_manager_client_composite_operations.create_job_and_wait_for_state(
                create_job_details,
                wait_for_states=[OciState.FAILED.value, OciState.SUCCEEDED.value],
                waiter_kwargs={
                    "max_wait_seconds": timeout_seconds,
                    "succeed_on_not_found": False,
                    "max_interval_seconds": interval_wait,
                    "wait_callback": lambda index, res: log.info(
                        f"_apply_job_from_stack: {str(index)} -> {str(res.data.lifecycle_state)}"
                    ),
                },
            )
            log.info(f"Job run ended with {job.data.lifecycle_state} state")
            log.info(self._resource_manager_client.get_job_logs_content(job.data.id).data)
            if job.data.lifecycle_state == OciState.FAILED.value:
                raise RuntimeError(f"Job run ended with {job.data.lifecycle_state}")
        except Exception as e:
            log.info(f"Exception raised during apply_job_from_stack {e}: destroying")
            raise
        # on success, we return the jobs output - list
        items = self._resource_manager_client.list_job_outputs(job.data.id).data.items
        for item in items:
            if item.output_name == "oci_ccm_config":
                return item.output_value
        raise RuntimeError(f"Missing oci_ccm_config for stack {stack_id}")

    @staticmethod
    def _waiter_status(client_callback: Callable, name: str, status: str, **callback_kwargs) -> None:
        def is_status():
            data = client_callback(**callback_kwargs).data
            waiting_to = [obj for obj in data if obj.display_name == name]
            # limit to
            assert len(waiting_to) == 1, "Expecting for one volume with same name"
            return waiting_to[0].lifecycle_state == status

        waiting.wait(
            lambda: is_status(),
            timeout_seconds=120,
            sleep_seconds=5,
            waiting_for="Resource to be created",
        )

    @property
    def terraform_vm_name_key(self) -> str:
        return "display_name"

    @property
    def terraform_vm_resource_type(self) -> str:
        return "oci_core_instance"

    def list_nodes(self) -> List[Node]:
        pass

    def list_disks(self, node_name: str) -> List[Disk]:
        pass

    def list_networks(self) -> List[Any]:
        pass

    def list_leases(self, network_name: str) -> List[Any]:
        pass

    def shutdown_node(self, node_name: str) -> None:
        pass

    def shutdown_all_nodes(self) -> None:
        pass

    def start_node(self, node_name: str, check_ips: bool) -> None:
        pass

    def start_all_nodes(self) -> List[Node]:
        pass

    def restart_node(self, node_name: str) -> None:
        pass

    def format_node_disk(self, node_name: str, disk_index: int = 0) -> None:
        pass

    def format_all_node_disks(self) -> None:
        pass

    def attach_test_disk(self, node_name: str, disk_size: int, bootable=False, persistent=False, with_wwn=False):
        """Attaches a test disk. That disk can later be detached with `detach_all_test_disks`.

        :param with_wwn: Weather the disk should have a WWN(World Wide Name), Having a WWN creates a disk by-id link
        :param node_name: Node to attach disk to
        :param disk_size: Size of disk to attach
        :param bootable: Whether to format an MBR sector at the beginning of the disk
        :param persistent: Whether the disk should survive shutdowns
        """
        pass

    def detach_all_test_disks(self, node_name: str):
        """Detaches all test disks created by `attach_test_disk`.

        :param node_name: Node to detach disk from
        """
        pass

    def get_ingress_and_api_vips(self) -> dict:
        pass

    def destroy_all_nodes(self) -> None:
        log.info("OCI Destroying all nodes")
        for resource in self._cleanup_resources[::-1]:
            resource()
        pass

    def get_cluster_network(self) -> str:
        pass

    def setup_time(self) -> str:
        pass

    def prepare_nodes(self) -> None:
        log.info("OCI prepare all nodes")
        bucket_name = random_name("bucket-")
        namespace = self._create_bucket(bucket_name)
        self._upload_iso_to_bucket(self._entity_config.iso_download_path, namespace, bucket_name)
        url_path = self._create_pre_authenticated(
            random_name("preauth-"), self._entity_config.iso_download_path, namespace, bucket_name
        )

        terraform_variables = self._terraform_variables(
            cluster_name=self._entity_config.entity_name,
            image_source_uri=url_path,
            control_plane_shape=self._config.oci_controller_plane_shape,
            compute_shape=self._config.oci_compute_shape,
            compute_count=str(self._config.workers_count),
            base_dns=self._entity_config.base_dns_domain,
        )
        stack_id = self._create_stack(
            random_name("stack-"), namespace, bucket_name, self._config.oci_infrastructure_zip_file, terraform_variables
        )
        terraform_output = self._apply_job_from_stack(stack_id, random_name("job-"))
        self.cloud_provider = terraform_output

    def is_active(self, node_name) -> bool:
        pass

    def set_boot_order(self, node_name: str, cd_first: bool = False, cdrom_iso_path: str = None) -> None:
        pass

    def set_per_device_boot_order(self, node_name, key: Callable[[Disk], int]) -> None:
        """Set the boot priority for every disk.

        It sorts the disk according to the key function result
        :param node_name: The node to change its boot order
        :param key: a key function that gets a Disk object and decide it's priority
        """
        pass

    def get_node_ips_and_macs(self, node_name) -> Tuple[List[str], List[str]]:
        pass

    def set_single_node_ip(self, ip) -> None:
        pass

    def get_host_id(self, node_name: str) -> str:
        pass

    def get_cpu_cores(self, node_name: str) -> int:
        pass

    def set_cpu_cores(self, node_name: str, core_count: int) -> None:
        pass

    def get_ram_kib(self, node_name: str) -> int:
        pass

    def set_ram_kib(self, node_name: str, ram_kib: int) -> None:
        pass

    def get_primary_machine_cidr(self) -> Optional[str]:
        # Default to auto resolve by the cluster. see cluster.get_primary_machine_cidr
        return None

    def get_provisioning_cidr(self) -> Optional[str]:
        return None

    def attach_interface(self, node_name, network_xml: str) -> Tuple[libvirt.virNetwork, str]:
        pass

    def add_interface(self, node_name, network_name, target_interface: str) -> str:
        pass

    def undefine_interface(self, node_name: str, mac: str):
        pass

    def create_network(self, network_xml: str) -> libvirt.virNetwork:
        pass

    def get_network_by_name(self, network_name: str) -> libvirt.virNetwork:
        pass

    def wait_till_nodes_are_ready(self, network_name: str = None):
        """If not overridden - do not wait."""
        pass

    def destroy_network(self, network: libvirt.virNetwork):
        pass

    def notify_iso_ready(self) -> None:
        pass

    def set_dns(self, api_ip: str, ingress_ip: str) -> None:
        pass

    def set_dns_for_user_managed_network(self) -> None:
        pass

    def set_ipxe_url(self, network_name: str, ipxe_url: str):
        pass

    def get_day2_static_network_data(self):
        pass
