from enum import Enum
from typing import List, Tuple, Union

import oci
from oci.core import VirtualNetworkClient
from oci.core.models import Instance

import consts
from assisted_test_infra.test_infra import BaseClusterConfig
from assisted_test_infra.test_infra.controllers.node_controllers.tf_controller import TFController
from assisted_test_infra.test_infra.helper_classes.config import BaseNodesConfig
from assisted_test_infra.test_infra.helper_classes.config.base_oci_config import BaseOciConfig
from service_client import log

import waiting


class OciInstanceState(Enum):
    RUNNING = "RUNNING"
    STARTING = "STARTING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    TERMINATING = "TERMINATING"
    TERMINATED = "TERMINATED"
    RESETTING = "RESETTING"
    RESTARTING = "RESTARTING"


class OciVolumesState(Enum):
    AVAILABLE = "AVAILABLE"


class OciInstanceAction(Enum):
    START = "START"
    STOP = "STOP"
    SOFTRESET = "SOFTRESET"


class OciController(TFController):
    _config: BaseOciConfig

    def __init__(self, config: BaseNodesConfig, cluster_config: BaseClusterConfig):
        super().__init__(config, cluster_config)
        self._virtual_network_client: VirtualNetworkClient = None

    def get_all_vars(self):
        tfvars = super(OciController, self).get_all_vars()
        tfvars["unique_id"] = self._entity_config.entity_name.suffix
        tfvars["master_memory_gib"] = self._config.master_memory / consts.MiB_UNITS
        tfvars["worker_memory_gib"] = self._config.worker_memory / consts.MiB_UNITS
        tfvars["master_disk_size_gib"] = self._config.master_disk / consts.GB

        # Minimal disk size on OCI is 50GB
        if self._config.worker_disk == consts.resources.DEFAULT_WORKER_DISK:
            self._config.worker_disk = 50 * consts.GB

        tfvars["worker_disk_size_gib"] = self._config.worker_disk / consts.GB
        return tfvars

    @property
    def terraform_vm_name_key(self):
        return "display_name"

    @property
    def terraform_vm_resource_type(self) -> str:
        return "oci_core_instance"

    def _get_provider_client(self) -> object:
        oci_config = self._config.get_provider_config()

        # Raise exception if failed
        oci.config.validate_config(oci_config)
        self._virtual_network_client = oci.core.VirtualNetworkClient(oci_config)
        self._compute_client = oci.core.ComputeClient(oci_config)
        self._volume_client = oci.core.BlockstorageClient(oci_config)
        # self._provider_client is self._compute_client
        return self._compute_client

    def _get_provider_vm(self, tf_vm_name: str) -> Union[Instance, None]:
        vm_attributes = self._get_vm(tf_vm_name)["attributes"]

        oci_instances = self._compute_client.list_instances(self._config.oci_compartment_oicd).data
        for instance in oci_instances:
            if instance.id == vm_attributes["id"]:
                return instance

        raise ValueError(f"Can't find node with name: {tf_vm_name}")

    def start_node(self, node_name: str, check_ips: bool) -> None:
        """
        :raises ValueError if node_name does not exist
        """
        instance = self._get_provider_vm(node_name)
        if instance.lifecycle_state != OciInstanceState.RUNNING.value:
            log.info(f"Powering on OCI instance {node_name}")
            self._instance_action(instance, OciInstanceAction.START)
        else:
            log.warning(
                f"Attempted to power on node {node_name}, "
                f"but the instance is already on - lifecycle_state={instance.lifecycle_state}"
            )

    def shutdown_node(self, node_name: str) -> None:
        instance = self._get_provider_vm(node_name)
        if instance.lifecycle_state != OciInstanceState.STOPPED.value:
            log.info(f"Powering off OCI instance {node_name}")
            self._instance_action(instance, OciInstanceAction.STOP)

        else:
            log.warning(
                f"Attempted to power off node {node_name}, "
                f"but the instance is already off - lifecycle_state={instance.lifecycle_state}"
            )

    def _instance_action(self, instance: Instance, action: OciInstanceAction):
        response = self._compute_client.instance_action(instance_id=instance.id, action=action.value)
        assert response.status == 200, f"Failed to {action.value.lower()} {instance.display_name} OCI instance"

    @staticmethod
    def _waiter_status(client_callback, name, status, **callback_kwargs):
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

    def restart_node(self, node_name: str) -> None:
        log.info(f"Restarting OCI instance {node_name}")
        instance = self._get_provider_vm(node_name)
        self._instance_action(instance, OciInstanceAction.SOFTRESET)

    def is_active(self, node_name: str) -> bool:
        instance = self._get_provider_vm(node_name)
        return instance.lifecycle_state == OciInstanceState.RUNNING.value

    def get_cpu_cores(self, node_name: str) -> int:
        return self._get_vm(node_name)["attributes"]["shape_config"][0]["ocpus"]

    def get_ram_kib(self, node_name: str) -> int:
        return self._get_vm(node_name)["attributes"]["shape_config"][0]["memory_in_gbs"] * 1024 * 1024

    def get_node_ips_and_macs(self, node_name) -> Tuple[List[str], List[str]]:
        vm_attributes = self._get_vm(node_name)["attributes"]
        instance_id = vm_attributes["id"]

        vnics = self._compute_client.list_vnic_attachments(
            self._config.oci_compartment_oicd, instance_id=instance_id
        ).data
        mac_addresses = [self._virtual_network_client.get_vnic(vnic.vnic_id).data.mac_address for vnic in vnics]
        ip_addresses = [self._virtual_network_client.get_vnic(vnic.vnic_id).data.private_ip for vnic in vnics]

        return ip_addresses, mac_addresses

    def set_dns(self, api_ip: str, ingress_ip: str) -> None:
        return

    def attach_test_disk(self, node_name: str, disk_size: int, bootable=False, persistent=False, with_wwn=False):
        """Attach disk to OCI instance.

        Create a volume , configure with same domain as instance
        Attach the volume to the instance
        Disk size > 50G
        """
        instance = self._get_provider_vm(node_name)
        disk_type = "paravirtualized"
        volume_details = oci.core.models.CreateVolumeDetails(compartment_id=self._config.oci_compartment_oicd,
                                                             display_name=node_name, size_in_gbs=disk_size,
                                                             availability_domain=instance.availability_domain)

        vol = self._volume_client.create_volume(create_volume_details=volume_details).data
        self._waiter_status(self._volume_client.list_volumes, node_name, OciVolumesState.AVAILABLE.value,
                            availability_domain=instance.availability_domain,
                            compartment_id=self._config.oci_compartment_oicd)

        attach_details = oci.core.models.AttachParavirtualizedVolumeDetails(instance_id=instance.id, volume_id=vol.id,
                                                                            type=disk_type)
        self._compute_client.attach_volume(attach_volume_details=attach_details)

    def detach_all_test_disks(self, node_name):
        instance = self._get_provider_vm(node_name)
        volumes = self._compute_client.list_volume_attachments(availability_domain=instance.availability_domain,
                                                               instance_id=instance.id,
                                                               compartment_id=self._config.oci_compartment_oicd).data
        for volume in volumes:
            self._compute_client.detach_volume(volume_attachment_id=volume.id)
