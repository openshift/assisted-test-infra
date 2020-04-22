import waiting
import json
from tqdm import tqdm
import utils
import consts
from bm_inventory_client import ApiClient, Configuration, api, models


class InventoryClient(object):

    def __init__(self, inventory_url):
        self.inventory_url = inventory_url
        configs = Configuration()
        configs.host = self.inventory_url + "/api/bm-inventory/v1"
        self.api = ApiClient(configuration=configs)
        self.client = api.InventoryApi(api_client=self.api)

    def wait_for_api_readiness(self):
        print("Waiting for inventory api to be ready")
        waiting.wait(lambda: self.clusters_list() is not None,
                     timeout_seconds=consts.WAIT_FOR_BM_API,
                     sleep_seconds=5, waiting_for="Wait till inventory is ready",
                     expected_exceptions=Exception)

    def create_cluster(self, name, ssh_public_key=None, **cluster_params):
        cluster = models.ClusterUpdateParams(name=name, ssh_public_key=ssh_public_key,  **cluster_params)
        print("Creating cluster with params", cluster.__dict__)
        result = self.client.register_cluster(new_cluster_params=cluster)
        return result

    def get_cluster_hosts(self, cluster_id):
        print("Getting registered nodes for cluster", cluster_id)
        return self.client.list_hosts(cluster_id=cluster_id)

    def get_hosts_in_status(self, cluster_id, status):
        hosts = self.get_cluster_hosts(cluster_id)
        return [hosts for host in hosts if host["status"] == status]

    def clusters_list(self):
        return self.client.list_clusters()

    def cluster_get(self, cluster_id):
        print("Getting cluster with id", cluster_id)
        return self.client.get_cluster(cluster_id=cluster_id)

    def _download(self, response, file_path):
        progress = tqdm(iterable=response.read_chunked())
        with open(file_path, 'wb') as f:
            for chunk in progress:
                f.write(chunk)
        progress.close()

    def download_image(self, cluster_id, image_path):
        print("Downloading image for cluster", cluster_id, "to", image_path)
        response = self.client.download_cluster_iso(cluster_id=cluster_id, _preload_content=False)
        self._download(response=response, file_path=image_path)

    def set_hosts_roles(self, cluster_id, hosts_with_roles):
        print("Setting roles for hosts", hosts_with_roles, "in cluster", cluster_id)
        hosts = {"hostsRoles": hosts_with_roles}
        return self.client.update_cluster(cluster_id=cluster_id, cluster_update_params=hosts)

    def update_cluster(self, cluster_id, update_params):
        print("Updating cluster", cluster_id, "params", update_params)
        return self.client.update_cluster(cluster_id=cluster_id, cluster_update_params=update_params)

    def delete_cluster(self, cluster_id):
        print("Deleting cluster", cluster_id)
        self.client.deregister_cluster(cluster_id=cluster_id)

    def get_hosts_id_with_macs(self, cluster_id):
        hosts = self.get_cluster_hosts(cluster_id)
        hosts_data = {}
        for host in hosts:
            hw = json.loads(host.hardware_info)
            hosts_data[host.id] = [nic["mac"] for nic in hw["nics"]]
        return hosts_data

    def download_and_save_file(self, cluster_id, file_name, file_path):
        print("Downloading", file_name, "to", file_path)
        response = self.client.download_cluster_files(cluster_id=cluster_id, file_name=file_name,
                                                      _preload_content=False)
        with open(file_path, "wb") as _file:
            _file.write(response.data)

    def download_kubeconfig(self, cluster_id, kubeconfig_path):
        self.download_and_save_file(cluster_id=cluster_id, file_name="kubeconfig", file_path=kubeconfig_path)

    def install_cluster(self, cluster_id):
        print("Installing cluster", cluster_id)
        return self.client.install_cluster(cluster_id=cluster_id)


def create_client(wait_for_url=True):
    if wait_for_url:
        i_url = utils.get_service_url_with_retries("bm-inventory")
    else:
        i_url = utils.get_service_url("bm-inventory")
    print("Inventory url", i_url)
    client = InventoryClient(inventory_url=i_url)
    client.wait_for_api_readiness()
    return client
