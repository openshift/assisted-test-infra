import waiting
import json
from tqdm import tqdm
import utils
import consts
from bm_inventory_client import ApiClient, Configuration, api, models
from logger import log


class InventoryClient(object):

    def __init__(self, inventory_url):
        self.inventory_url = inventory_url
        configs = Configuration()
        configs.host = self.inventory_url + "/api/bm-inventory/v1"
        self.api = ApiClient(configuration=configs)
        self.client = api.InventoryApi(api_client=self.api)

    def wait_for_api_readiness(self):
        log.info("Waiting for inventory api to be ready")
        waiting.wait(lambda: self.clusters_list() is not None,
                     timeout_seconds=consts.WAIT_FOR_BM_API,
                     sleep_seconds=5, waiting_for="Wait till inventory is ready",
                     expected_exceptions=Exception)

    def create_cluster(self, name, ssh_public_key=None, **cluster_params):
        cluster = models.ClusterCreateParams(name=name, ssh_public_key=ssh_public_key,  **cluster_params)
        log.info("Creating cluster with params %s", cluster.__dict__)
        result = self.client.register_cluster(new_cluster_params=cluster)
        return result

    def get_cluster_hosts(self, cluster_id):
        log.info("Getting registered nodes for cluster %s", cluster_id)
        return self.client.list_hosts(cluster_id=cluster_id)

    def get_hosts_in_status(self, cluster_id, status):
        hosts = self.get_cluster_hosts(cluster_id)
        return [hosts for host in hosts if host["status"] == status]

    def clusters_list(self):
        return self.client.list_clusters()

    def cluster_get(self, cluster_id):
        log.info("Getting cluster with id %s", cluster_id)
        return self.client.get_cluster(cluster_id=cluster_id)

    def _download(self, response, file_path):
        progress = tqdm(iterable=response.read_chunked())
        with open(file_path, 'wb') as f:
            for chunk in progress:
                f.write(chunk)
        progress.close()

    def generate_image(self, cluster_id, ssh_key, proxy_url=None):
        log.info("Generating image for cluster %s", cluster_id)
        image_create_params = models.ImageCreateParams(ssh_public_key=ssh_key)
        if proxy_url:
            image_create_params.proxy_url = proxy_url
        log.info("Generating image with params %s", image_create_params.__dict__)
        return self.client.generate_cluster_iso(cluster_id=cluster_id, image_create_params=image_create_params)

    def download_image(self, cluster_id, image_path, image_id):
        log.info("Downloading image for cluster %s to %s", cluster_id, image_path)
        response = self.client.download_cluster_iso(cluster_id=cluster_id, image_id=image_id,
                                                    _preload_content=False)
        self._download(response=response, file_path=image_path)

    def generate_and_download_image(self, cluster_id, ssh_key, image_path, proxy_url=None):
        image = self.generate_image(cluster_id=cluster_id, ssh_key=ssh_key, proxy_url=proxy_url)
        self.download_image(cluster_id=cluster_id, image_path=image_path, image_id=image.image_id)

    def set_hosts_roles(self, cluster_id, hosts_with_roles):
        log.info("Setting roles for hosts %s in cluster %s", hosts_with_roles, cluster_id)
        hosts = {"hostsRoles": hosts_with_roles}
        return self.client.update_cluster(cluster_id=cluster_id, cluster_update_params=hosts)

    def update_cluster(self, cluster_id, update_params):
        log.info("Updating cluster %s with params %s", cluster_id, update_params)
        return self.client.update_cluster(cluster_id=cluster_id, cluster_update_params=update_params)

    def delete_cluster(self, cluster_id):
        log.info("Deleting cluster %s", cluster_id)
        self.client.deregister_cluster(cluster_id=cluster_id)

    def get_hosts_id_with_macs(self, cluster_id):
        hosts = self.get_cluster_hosts(cluster_id)
        hosts_data = {}
        for host in hosts:
            hw = json.loads(host.hardware_info)
            hosts_data[host.id] = [nic["mac"] for nic in hw["nics"]]
        return hosts_data

    def download_and_save_file(self, cluster_id, file_name, file_path):
        log.info("Downloading %s to %s", file_name, file_path)
        response = self.client.download_cluster_files(cluster_id=cluster_id, file_name=file_name,
                                                      _preload_content=False)
        with open(file_path, "wb") as _file:
            _file.write(response.data)

    def download_kubeconfig(self, cluster_id, kubeconfig_path):
        self.download_and_save_file(cluster_id=cluster_id, file_name="kubeconfig", file_path=kubeconfig_path)

    def install_cluster(self, cluster_id):
        log.info("Installing cluster %s", cluster_id)
        return self.client.install_cluster(cluster_id=cluster_id)


def create_client(wait_for_url=True):
    if wait_for_url:
        i_url = utils.get_service_url_with_retries("bm-inventory")
    else:
        i_url = utils.get_service_url("bm-inventory")
    log.info("Inventory url %s", i_url)
    client = InventoryClient(inventory_url=i_url)
    client.wait_for_api_readiness()
    return client
