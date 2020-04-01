import waiting
import json
from tqdm import tqdm
from bm_inventory_client import ApiClient, Configuration, api


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
                     timeout_seconds=180,
                     sleep_seconds=5, waiting_for="Wait till inventory is ready",
                     expected_exceptions=Exception)

    def create_cluster(self, name, openshift_version="4.5", base_dns_domain="test-infra.redhat", ssh_public_key=None,
                       api_vip="api-test-infra.redhat"):

        data = {
            "name": name,
            "openshift_version": openshift_version,
            "baseDnsDomain": base_dns_domain,
            "apiVip": api_vip,
            "sshPublicKey": ssh_public_key
        }
        print("Creating cluster with params", data)
        result = self.client.register_cluster(new_cluster_params=data)
        return result

    def get_cluster_hosts(self, cluster_id):
        print("Getting registered nodes for cluster", cluster_id)
        return self.client.list_hosts(cluster_id=cluster_id)

    def clusters_list(self):
        return self.client.list_clusters()

    def cluster_get(self, cluster_id):
        print("Getting cluster with id", cluster_id)
        return self.client.get_cluster(cluster_id=cluster_id)

    def download_image(self, cluster_id, image_path):
        print("Downloading image for cluster", cluster_id, "to", image_path)
        response = self.client.download_cluster_iso(cluster_id=cluster_id, _preload_content=False)
        progress = tqdm(iterable=response.read_chunked())
        with open(image_path, 'wb') as f:
            for chunk in progress:
                f.write(chunk)
        progress.close()

    def set_hosts_roles(self, cluster_id, hosts_with_roles):
        print("Setting roles for hosts", hosts_with_roles, "in cluster", cluster_id)
        hosts = {"hostsRoles": hosts_with_roles}
        res = self.client.update_cluster(cluster_id=cluster_id, cluster_update_params=hosts, _preload_content=False)
        return json.loads(res.data)
