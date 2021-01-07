# -*- coding: utf-8 -*-
import json
import os
import base64
import requests
import time

from test_infra import consts, utils
import shutil
import waiting
from assisted_service_client import ApiClient, Configuration, api, models
from logger import log
from retry import retry


class InventoryClient(object):
    def __init__(self, inventory_url, offline_token, pull_secret):
        self.inventory_url = inventory_url
        configs = Configuration()
        configs.host = self.inventory_url + "/api/assisted-install/v1"
        configs.verify_ssl = False
        self.set_config_auth(configs, offline_token)
        self._set_x_secret_key(configs, pull_secret)

        self.api = ApiClient(configuration=configs)
        self.client = api.InstallerApi(api_client=self.api)
        self.events = api.EventsApi(api_client=self.api)
        self.versions = api.VersionsApi(api_client=self.api)

    def set_config_auth(self, c, offline_token):
        if not offline_token:
            log.info("OFFLINE_TOKEN not set, skipping authentication headers")
            return

        def refresh_api_key(config):
            # Get the properly padded key segment
            auth = config.api_key.get('Authorization', None)
            if auth != None:
                segment = auth.split('.')[1]
                padding = len(segment) % 4
                segment = segment + padding * '='

                expires_on = json.loads(base64.b64decode(segment))['exp']

                # if this key doesn't expire or if it has more than 10 minutes left, don't refresh
                remaining = expires_on - time.time()
                if expires_on == 0 or remaining > 600:
                    return

            # fetch new key if expired or not set yet
            params = {
                "client_id": "cloud-services",
                "grant_type": "refresh_token",
                "refresh_token": offline_token,
            }

            log.info("Refreshing API key")
            response = requests.post(os.environ.get("SSO_URL"), data=params)
            response.raise_for_status()

            config.api_key['Authorization'] = response.json()['access_token']

        c.api_key_prefix['Authorization'] = 'Bearer'
        c.refresh_api_key_hook = refresh_api_key

    def _set_x_secret_key(self, c, pull_secret):
        if not pull_secret:
            log.info("pull secret not set, skipping agent authentication headers")
            return

        log.info("Setting X-Secret-Key")
        c.api_key['X-Secret-Key'] = json.loads(pull_secret)['auths']['cloud.openshift.com']['auth']

    def wait_for_api_readiness(self):
        log.info("Waiting for inventory api to be ready")
        waiting.wait(
            lambda: self.clusters_list() is not None,
            timeout_seconds=consts.WAIT_FOR_BM_API,
            sleep_seconds=5,
            waiting_for="Wait till inventory is ready",
            expected_exceptions=Exception,
        )

    def create_cluster(self, name, ssh_public_key=None, **cluster_params):
        cluster = models.ClusterCreateParams(
            name=name, ssh_public_key=ssh_public_key, **cluster_params
        )
        log.info("Creating cluster with params %s", cluster.__dict__)
        result = self.client.register_cluster(new_cluster_params=cluster)
        return result

    def create_day2_cluster(self, name, cluster_uuid, **cluster_params):
        cluster = models.AddHostsClusterCreateParams(
            name=name, id=cluster_uuid, **cluster_params
        )
        log.info("Creating day 2 cluster with params %s", cluster.__dict__)
        result = self.client.register_add_hosts_cluster(new_add_hosts_cluster_params=cluster)
        return result

    def get_cluster_hosts(self, cluster_id):
        log.info("Getting registered nodes for cluster %s", cluster_id)
        return self.client.list_hosts(cluster_id=cluster_id)

    def get_hosts_in_statuses(self, cluster_id, statuses):
        hosts = self.get_cluster_hosts(cluster_id)
        return [host for host in hosts if host["status"] in statuses]

    def get_hosts_in_error_status(self, cluster_id):
        return self.get_hosts_in_statuses(cluster_id, [consts.NodesStatus.ERROR])

    def clusters_list(self):
        return self.client.list_clusters()

    def cluster_get(self, cluster_id):
        log.info("Getting cluster with id %s", cluster_id)
        return self.client.get_cluster(cluster_id=cluster_id)

    def _download(self, response, file_path, verify_file_size=False):
        with open(file_path, "wb") as f:
            shutil.copyfileobj(response, f)
        if verify_file_size:
            content_length = int(response.headers['content-length'])
            actual_file_size = os.path.getsize(file_path)
            if actual_file_size < content_length:
                raise RuntimeError(
                    f'Could not complete ISO download {file_path}. '\
                    f'Actual size: {actual_file_size}. Expected size: {content_length}'
                    )

    def generate_image(self, cluster_id, ssh_key, static_ips):
        log.info("Generating image for cluster %s", cluster_id)
        image_create_params = models.ImageCreateParams(ssh_public_key=ssh_key, static_ips_config=static_ips)
        log.info("Generating image with params %s", image_create_params.__dict__)
        return self.client.generate_cluster_iso(
            cluster_id=cluster_id, image_create_params=image_create_params
        )

    @retry(exceptions=RuntimeError, tries=2, delay=3)
    def download_image(self, cluster_id, image_path):
        log.info("Downloading image for cluster %s to %s", cluster_id, image_path)
        response = self.client.download_cluster_iso_with_http_info(
            cluster_id=cluster_id, _preload_content=False
        )
        response_obj = response[0]
        self._download(response=response_obj, file_path=image_path, verify_file_size=True)

    def generate_and_download_image(self, cluster_id, ssh_key, image_path, static_ips=None):
        self.generate_image(cluster_id=cluster_id, ssh_key=ssh_key, static_ips=static_ips)
        self.download_image(cluster_id=cluster_id, image_path=image_path)

    def update_hosts(self, cluster_id, hosts_with_roles, hosts_names=None):
        log.info(
            "Setting roles for hosts %s in cluster %s", hosts_with_roles, cluster_id
        )
        hosts = models.ClusterUpdateParams(hosts_roles=hosts_with_roles, hosts_names=hosts_names)
        return self.client.update_cluster(
            cluster_id=cluster_id, cluster_update_params=hosts
        )

    def set_pull_secret(self, cluster_id, pull_secret):
        log.info(
            "Setting pull secret for cluster %s", cluster_id
        )
        update_params = models.ClusterUpdateParams(pull_secret=pull_secret)
        return self.client.update_cluster(
            cluster_id=cluster_id, cluster_update_params=update_params)

    def update_cluster(self, cluster_id, update_params):
        log.info("Updating cluster %s with params %s", cluster_id, update_params)
        return self.client.update_cluster(
            cluster_id=cluster_id, cluster_update_params=update_params
        )

    def delete_cluster(self, cluster_id):
        log.info("Deleting cluster %s", cluster_id)
        self.client.deregister_cluster(cluster_id=cluster_id)

    def get_hosts_id_with_macs(self, cluster_id):
        hosts = self.get_cluster_hosts(cluster_id)
        hosts_data = {}
        for host in hosts:
            inventory = json.loads(host.get("inventory", '{"interfaces":[]}'))
            hosts_data[host["id"]] = [
                interface["mac_address"] for interface in inventory["interfaces"]
            ]
        return hosts_data

    def get_host_by_mac(self, cluster_id, mac):
        hosts = self.get_cluster_hosts(cluster_id)

        for host in hosts:
            inventory = json.loads(host.get("inventory", '{"interfaces":[]}'))
            if mac.lower() in [
                interface["mac_address"].lower()
                for interface in inventory["interfaces"]
            ]:
                return host

    def get_host_by_name(self, cluster_id, host_name):
        hosts = self.get_cluster_hosts(cluster_id)

        for host in hosts:
            hostname = host.get('requested_hostname')
            if hostname == host_name:
                log.info(f"Requested host by name: {host_name}, host details: {host}")
                return host

    def download_and_save_file(self, cluster_id, file_name, file_path):
        log.info("Downloading %s to %s", file_name, file_path)
        response = self.client.download_cluster_files(
            cluster_id=cluster_id, file_name=file_name, _preload_content=False
        )
        with open(file_path, "wb") as _file:
            _file.write(response.data)

    def download_kubeconfig_no_ingress(self, cluster_id, kubeconfig_path):
        log.info("Downloading kubeconfig-noingress to %s", kubeconfig_path)
        self.download_and_save_file(
            cluster_id=cluster_id,
            file_name="kubeconfig-noingress",
            file_path=kubeconfig_path,
        )

    def download_ignition_files(self, cluster_id, destination):
        log.info("Downloading cluster %s ignition files to %s", cluster_id, destination)

        for ignition_file in ["bootstrap.ign", "master.ign", "worker.ign", "install-config.yaml"]:
            response = self.client.download_cluster_files(
                cluster_id=cluster_id, file_name=ignition_file, _preload_content=False
            )
            with open(os.path.join(destination, ignition_file), "wb") as _file:
                _file.write(response.data)

    def download_host_ignition(self, cluster_id, host_id, destination):
        log.info("Downloading host %s cluster %s ignition files to %s", host_id, cluster_id, destination)

        response = self.client.download_host_ignition(
            cluster_id=cluster_id, host_id=host_id, _preload_content=False
        )
        with open(os.path.join(destination, f"host_{host_id}.ign"), "wb") as _file:
            _file.write(response.data)

    def download_kubeconfig(self, cluster_id, kubeconfig_path):
        log.info("Downloading kubeconfig to %s", kubeconfig_path)
        response = self.client.download_cluster_kubeconfig(
            cluster_id=cluster_id, _preload_content=False
        )
        with open(kubeconfig_path, "wb") as _file:
            _file.write(response.data)

    def install_cluster(self, cluster_id):
        log.info("Installing cluster %s", cluster_id)
        return self.client.install_cluster(cluster_id=cluster_id)

    def install_day2_cluster(self, cluster_id):
        log.info("Installing day2 cluster %s", cluster_id)
        return self.client.install_hosts(cluster_id=cluster_id)

    def install_day2_host(self, cluster_id, host_id):
        log.info("Installing day2 host %s, cluster %s", host_id, cluster_id)
        return self.client.install_host(cluster_id=cluster_id, host_id=host_id)

    def download_cluster_logs(self, cluster_id, output_file):
        log.info("Downloading cluster logs to %s", output_file)
        response = self.client.download_cluster_logs(
            cluster_id=cluster_id, _preload_content=False
        )
        with open(output_file, "wb") as _file:
            _file.write(response.data)

    def get_events(self, cluster_id, host_id=''):
        response = self.events.list_events(
            cluster_id=cluster_id, host_id=host_id, _preload_content=False
        )

        return json.loads(response.data)

    def download_cluster_events(self, cluster_id, output_file):
        log.info("Downloading cluster events to %s", output_file)

        with open(output_file, "wb") as _file:
            _file.write(json.dumps(self.get_events(cluster_id), indent=4).encode())

    def download_host_logs(self, cluster_id, host_id, output_file):
        log.info("Downloading host logs to %s", output_file)
        response = self.client.download_host_logs(
            cluster_id=cluster_id, host_id=host_id, _preload_content=False
        )
        with open(output_file, "wb") as _file:
            _file.write(response.data)

    def cancel_cluster_install(self, cluster_id):
        log.info("Canceling installation of cluster %s", cluster_id)
        return self.client.cancel_installation(cluster_id=cluster_id)

    def reset_cluster_install(self, cluster_id):
        log.info("Reset installation of cluster %s", cluster_id)
        return self.client.reset_cluster(cluster_id=cluster_id)

    def disable_host(self, cluster_id, host_id):
        log.info(f"Disabling host: {host_id}, in cluster id: {cluster_id}")
        return self.client.disable_host(cluster_id=cluster_id, host_id=host_id)

    def set_cluster_proxy(self, cluster_id, http_proxy, https_proxy='', no_proxy=''):
        log.info(
            "Setting proxy for cluster %s", cluster_id
        )
        update_params = models.ClusterUpdateParams(
            http_proxy=http_proxy,
            https_proxy=https_proxy,
            no_proxy=no_proxy
        )
        return self.client.update_cluster(
            cluster_id=cluster_id, cluster_update_params=update_params
        )

    def get_cluster_install_config(self, cluster_id):
        log.info("Getting install-config for cluster %s", cluster_id)
        return self.client.get_cluster_install_config(cluster_id=cluster_id)

    def patch_cluster_discovery_ignition(self, cluster_id, ignition_info):
        log.info("Patching cluster %s discovery ignition", cluster_id)
        return self.client.update_discovery_ignition(cluster_id=cluster_id,
                                                     discovery_ignition_params=models.DiscoveryIgnitionParams(
                                                         config=json.dumps(ignition_info)))

    def get_cluster_discovery_ignition(self, cluster_id):
        log.info("Getting discovery ignition for cluster %s", cluster_id)
        return self.client.get_discovery_ignition(cluster_id=cluster_id, )

    def register_host(self, cluster_id, host_id):
        log.info(f"Registering host: {host_id} to cluster: {cluster_id}")
        host_params = models.HostCreateParams(host_id=host_id)
        self.client.register_host(cluster_id, host_params)

    def host_get_next_step(self, cluster_id, host_id):
        log.info(f"Getting next step for host: {host_id} in cluster: {cluster_id}")
        return self.client.get_next_steps(
            cluster_id=cluster_id, 
            host_id=host_id
        )

    def host_post_step_result(self, cluster_id, host_id, **kwargs):
        reply = models.StepReply(**kwargs)
        self.client.post_step_reply(cluster_id=cluster_id, host_id=host_id, reply=reply)

    def host_update_progress(self, cluster_id, host_id, current_stage, progress_info=None):
        host_progress = models.HostProgress(current_stage=current_stage, progress_info=progress_info)
        self.client.update_host_install_progress(
            cluster_id=cluster_id, 
            host_id=host_id, 
            host_progress=host_progress
        )

    def complete_cluster_installation(self, cluster_id, is_success, error_info=None):
        completion_params=models.CompletionParams(is_success=is_success, error_info=error_info)
        self.client.complete_installation(
            cluster_id=cluster_id, 
            completion_params=completion_params
        )

    def get_cluster_admin_credentials(self, cluster_id):
        return self.client.get_credentials(cluster_id=cluster_id)

    def get_versions(self):
        response = self.versions.list_component_versions()
        return json.loads(json.dumps(response.to_dict(), sort_keys=True, default=str))

    def get_openshift_versions(self):
        return self.versions.list_supported_openshift_versions()


def create_client(
    url,
    offline_token=utils.get_env('OFFLINE_TOKEN'),
    pull_secret="",
    wait_for_api=True
    ):
    log.info('Creating assisted-service client for url: %s', url)
    c = InventoryClient(url, offline_token, pull_secret)
    if wait_for_api:
        c.wait_for_api_readiness()
    return c
