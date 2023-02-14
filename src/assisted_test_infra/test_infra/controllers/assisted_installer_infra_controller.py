import logging
import time
from enum import Enum
from typing import Any

import kubernetes.client
import kubernetes.config
import kubernetes.dynamic
import waiting


class AssistedInstallerInfraController:
    """Manage hub cluster configuration changes via kubernetes commands.
    Allow to modify configmap and verify changes
    Allow to stop/start resources plus waiters
    for actions completed till pods deleted or created.
    Enable metrics to check memory leaks and cpu usage - TBD
    In order to access to data resource we:
    _get_resources_by_kind -> this is the kind of resource
    _get_obj_resources_by_name -> get the obj resource name
    """

    class Resources(Enum):
        CONFIGMAP = "ConfigMap"
        DEPLOYMENT = "Deployment"
        REPLICASET = "ReplicaSet"
        POD = "Pod"
        SERVICE = "Service"

    def __init__(self, global_variables):
        """
        Initialized k8_client
        """
        self.global_variables = global_variables
        self.k8s_client = self._init_k8s_client()
        # mapping for resources kind by enum
        self.mapping_resources = {
            self.Resources.CONFIGMAP.value: self.configmap_resource,
            self.Resources.DEPLOYMENT.value: self.deployment_resource,
            self.Resources.REPLICASET.value: self.replicaset_resource,
            self.Resources.POD.value: self.pod_resource,
            self.Resources.SERVICE.value: self.service_resource,
        }

    @staticmethod
    def _init_k8s_client() -> kubernetes.dynamic.DynamicClient:
        return kubernetes.dynamic.DynamicClient(
            kubernetes.client.api_client.ApiClient(
                configuration=kubernetes.config.load_kube_config(),
            ),
        )

    @property
    def namespace(self) -> str:
        return self.global_variables.namespace

    @property
    def configmap_resource(self) -> kubernetes.dynamic.Resource:
        return self._get_resources_by_kind(self.Resources.CONFIGMAP.value, "v1")

    @property
    def replicaset_resource(self) -> kubernetes.dynamic.Resource:
        return self._get_resources_by_kind(self.Resources.REPLICASET.value, "apps/v1")

    @property
    def deployment_resource(self) -> kubernetes.dynamic.Resource:
        return self._get_resources_by_kind(self.Resources.DEPLOYMENT.value, "apps/v1")

    @property
    def pod_resource(self) -> kubernetes.dynamic.Resource:
        return self._get_resources_by_kind(self.Resources.POD.value, "v1")

    @property
    def service_resource(self) -> kubernetes.dynamic.Resource:
        return self._get_resources_by_kind(self.Resources.SERVICE.value, "v1")

    @property
    def configmap_name(self) -> str:
        return self.global_variables.configmap

    @property
    def ai_base_version(self) -> str:
        return self.global_variables.ai_base_version

    @property
    def configmap_data(self) -> dict:
        config_map_store = self._get_obj_resources_by_name(self.Resources.CONFIGMAP.value, self.configmap_name)
        assert len(config_map_store) == 1, "configmap kind name should be unique"
        return dict(config_map_store[0])

    @property
    def assisted_service_name(self) -> str:
        return self.global_variables.deployment_service

    def resource_kind(self, name: str) -> kubernetes.dynamic.Resource:
        """Get the resource kind object by name
        :param name: ReplicaSet, Deployment, Pod, ConfigMap, Service, Pod
        :return: Resource object
        """
        return self.mapping_resources.get(name)

    def _get_resources_by_kind(self, kind_name: str, api_version: str) -> kubernetes.dynamic.Resource:
        """Get resource by api_version and kind
        :param kind_name: ReplicaSet, Deployment, Pod, ConfigMap, Service, Pod
        :param api_version: for Pod/service its v1 and others apps/v1
        :return: resource client based on type Pod , Service others.
        """
        return self.k8s_client.resources.get(api_version=api_version, kind=kind_name)

    def _get_obj_resources_by_name(
        self, resource_kind_name: str, name_begins_with: str, exact_match: bool = False
    ) -> list[kubernetes.dynamic.ResourceField]:
        """Get object by resource obj by namespace and begins name.
        In case calling to pod resource we may have multiple pods beginning
        the same name. assisted-service, assisted-service123 ...
        :param resource_kind_name: ReplicaSet, Deployment, Pod, ConfigMap, Service Pod
        :param name_begins_with: lookup name begins the same for all kinds
        :return: List of all objects beginning the same name for pods
        """
        all_resources = self.resource_kind(resource_kind_name).get(namespace=self.namespace, name=None)
        if not exact_match:
            logging.debug(
                f"_get_obj_resources_by_name resource_kind_name={resource_kind_name}"
                f" name_begins_with={name_begins_with} exact_match={exact_match}"
            )
            return [obj for obj in all_resources.items if obj.metadata.name.startswith(name_begins_with)]
        else:
            logging.debug(
                f"_get_obj_resources_by_name resource_kind_name={resource_kind_name} "
                f"name_begins_with={name_begins_with} exact_match={exact_match}"
            )
            return [obj for obj in all_resources.items if name_begins_with == obj.metadata.name]

    def _verify_resource_replicas(self, resource_type: str, resource_name: str, exact_match=False, count=1) -> None:
        resource = self._get_obj_resources_by_name(resource_type, resource_name, exact_match)
        assert len(resource) == count, f"{resource_type} repeated {len(resource)} times expected {count}"

    def _restart_deployment(self, deployment_name: str, test_name: str = "") -> None:
        logging.info(f"Deployment scale {deployment_name} to 0 for test {test_name} - waiting")
        self.change_deployment_scale(deployment_name, 0)
        logging.info(f"Deployment scale {deployment_name} to 1 for test {test_name} - waiting")
        self.change_deployment_scale(deployment_name, 1)

    def patch_resource(self, resource_kind_name: str, name: str, body: dict[str, Any]) -> kubernetes.client.api_client:
        """Patch change configuration for a resource object and verify
        configuration change really populated.
        :param resource_kind_name: ReplicaSet, Deployment, Pod, ConfigMap, Service Pod
        :param name: patch by the resource object name
        :param body:  dictionary to patch for a change
        :return: patch output
        """
        logging.info(f"patch_resource change kind={resource_kind_name} name={name} body={str(body)}")
        patch = self.resource_kind(resource_kind_name).patch(namespace=self.namespace, name=name, body=body)
        # verifying configuration to configmap , need to extend check for other resources
        assert self.verify_resource_data_exists(resource_kind_name, name, body), f"Patch {str(body)} could not found"
        return patch

    def verify_resource_data_exists(
        self, resource_kind_name: str, obj_resource_name: str, body_data: dict[str, Any]
    ) -> bool:
        """Verify changed resource obj data already configured by request
        Limited function - need to improve the code for deeper search - TBD
        :param resource_kind_name: ReplicaSet, Deployment, Pod, ConfigMap, Service Pod
        :param obj_resource_name: name of the resource obj to verify configuration
        :param body_data: body data configmap as dict body['data']
        :return: True if config match
        """

        assert len(body_data.keys()) == 1, "Could not find the root key for lookup change"
        body_key = list(body_data.keys())[0]

        resource_obj = self._get_obj_resources_by_name(resource_kind_name, obj_resource_name)
        assert len(resource_obj) == 1, f"{obj_resource_name} object name should be unique {resource_obj}"

        resource_obj = resource_obj[0][body_key]
        body = body_data[body_key]
        result = all(list(map(lambda key: body[key] == resource_obj[key], body)))
        return result

    def verify_deployments_are_ready(self) -> bool:
        """
        Verify that all deployments are in ready status
        :return:
        """
        deployments = self.resource_kind(self.Resources.DEPLOYMENT.value).get().items

        def check_ready_replicas(deployment):
            return deployment["status"].availableReplicas == 1 and deployment["status"].readyReplicas == 1

        is_ready = all(list(map(check_ready_replicas, deployments)))
        logging.info(f"verify_deployments_are_ready status: {str(deployments)}")
        return is_ready

    def wait_for_scale_config_change(
        self, resource_name: str, name: str, replicas_count: int, timeout=10, sleep=2
    ) -> None:
        """Verify that configuration changes in spec for Deployment and ReplicaSet
        We assume that replicas and development name appears only once and pods
        are duplicated.
        :param resource_kind_name: resource name from deployment or replicaset
        :param name: name of the resource - assisted-service
        :param replicas_count: total requested replicas to verify in the spec
        :param timeout: 10 second default
        :param sleep: 2 second interval
        :return:
        """
        waiting.wait(
            lambda: self._get_obj_resources_by_name(resource_name, name)[0].spec.replicas == replicas_count,
            timeout_seconds=timeout,
            sleep_seconds=sleep,
            waiting_for=f"replicas to change successfully to {replicas_count}",
        )

    def wait_for_pod_change(self, name: str, replicas_count: int, timeout=180, sleep=10, recover_time_pods=20) -> None:
        """Verify pod created / deleted based on replicas numbers
        In case we create pods (replicas) need to wait for a running state
        :param name: lookup name begins with assisted-service
        :param replicas_count: total number of replicas
        :param timeout: totl wait time till pods deleted or created ready
        :param sleep: sleep between interval
        :param recover_time_pods: after stop/start pod may take more time to load
        :return:
        """
        waiting.wait(
            lambda: len(self._get_obj_resources_by_name(self.Resources.POD.value, name)) == replicas_count,
            timeout_seconds=timeout,
            sleep_seconds=sleep,
            waiting_for=f"replicas to change successfully to {replicas_count} for {name}",
        )
        # In case the scale increased check if all pods are ready and active
        if replicas_count:

            def pods_are_running():
                # Waiter lambda verify all pods are running begins with the same name
                pods = self._get_obj_resources_by_name(self.Resources.POD.value, name)
                running = list(map(lambda pod: hasattr(pod.status, "phase") and pod.status.phase == "Running", pods))
                return all(running)

            waiting.wait(
                lambda: pods_are_running() is True,
                timeout_seconds=timeout,
                sleep_seconds=sleep,
                waiting_for="replicas to change successfully",
            )

        time.sleep(recover_time_pods)

    def change_deployment_scale(self, deployment_name: str, replicas_count: str) -> None:
        """Common code for scale up and down deployment
        We assume that assisted-service name is unique in deployment. other kinds
        name starts with same name with uuids like assisted-service-9fdd7f47-xd8vz
        :param deployment_name: assisted-service
        :param replicas_count: total number , 0 for stop 1 and more for start
        :return:
        """
        self._verify_resource_replicas(self.Resources.DEPLOYMENT.value, deployment_name)
        self._verify_resource_replicas(self.Resources.REPLICASET.value, deployment_name)

        body = {"spec": {"replicas": replicas_count}}
        # Patch change configuration
        self.patch_resource(self.Resources.DEPLOYMENT.value, deployment_name, body)
        self.wait_for_scale_config_change(self.Resources.DEPLOYMENT.value, deployment_name, replicas_count)
        self.wait_for_scale_config_change(self.Resources.REPLICASET.value, deployment_name, replicas_count)
        # When changed to zero pods with this name should be deleted.
        self.wait_for_pod_change(deployment_name, replicas_count)

    def change_configmap_data(
        self, dict_data: dict[str, Any], restart_deployment=True, deployment_name="assisted-service"
    ) -> None:
        """Accept data we would like to change and patch it to configmap
        Example:
            {data: {'ENABLE_UPGRADE_AGENT': 'True', 'AGENT_DOCKER_IMAGE':
             agent_docker_image + tag_version}}
        :param restart_deployment after configuration change
        :param deployment_name - the deployment name to scale down/up
        :param dict_data:
        :return:
        """
        body = dict_data
        self.patch_resource(self.Resources.CONFIGMAP.value, self.configmap_name, body)
        # stop /start development for service
        if restart_deployment:
            self._restart_deployment(deployment_name)

    def rollout_assisted_service(
        self, configmap_before: dict[str, Any], configmap_after: dict[str, Any], request_node_name: str
    ) -> None:
        """Rollout hub cluster configuration  to last changed configuration if needed
        When running test func and we chnage the configmap we must restore
        configuration and verify / wait till it is done properly
        :param configmap_before: configuration when test begins
        :param configmap_after: configuration post yield check for changed
        :param request_node_name: the rest_func name accepted by fixture
        :return:
        """
        if configmap_before != configmap_after:
            logging.debug(f"configmap data {self.configmap_name} changed during {request_node_name} - restoring")
            self.patch_resource(self.Resources.CONFIGMAP.value, self.configmap_name, {"data": configmap_before})
            self._restart_deployment(self.assisted_service_name, request_node_name)
        else:
            logging.info(f"configmap {self.configmap_name} was not changed during the test {request_node_name}")
