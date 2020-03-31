import requests
import waiting
from tqdm import tqdm


class InventoryClient(object):

    def __init__(self, inventory_url):
        self.inventory_url = inventory_url
        self.cluster_url = self.inventory_url + "/api/bm-inventory/v1/clusters/"

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
            "openshiftVersion": openshift_version,
            "baseDnsDomain": base_dns_domain,
            "apiVip": api_vip,
            "sshPublicKey": ssh_public_key
        }
        print("Creating cluster with params", data)
        result = requests.post(self.cluster_url, json=data)
        result.raise_for_status()
        return result.json()

    def get_cluster_hosts(self, cluster_id):
        print("Getting registered nodes for cluster", cluster_id)
        result = requests.get(self.cluster_url + cluster_id + "/hosts", timeout=5)
        # result = requests.get(self.cluster_url + cluster_id, timeout=5)
        result.raise_for_status()
        return result.json()

    def clusters_list(self):
        result = requests.get(self.cluster_url, timeout=5)
        result.raise_for_status()
        return result.json()

    def cluster_get(self, cluster_id):
        print("Getting cluster with id", cluster_id)
        result = requests.get(self.cluster_url + cluster_id, timeout=5)
        result.raise_for_status()
        return result.json()

    def download_image(self, cluster_id, image_path):
        print("Downloading image for cluster", cluster_id, "to", image_path)
        response = requests.get(self.cluster_url + cluster_id + "/actions/download", stream=True)
        response.raise_for_status()
        total_size = int(response.headers.get('content-length', 0))
        block_size = 1024
        progress = tqdm(iterable=response.iter_content(chunk_size=block_size), total=total_size) #, unit='iB', unit_scale=True)
        with open(image_path, 'wb') as f:
            for chunk in progress:
                f.write(chunk)
        progress.close()
        if total_size != 0 and progress.n != total_size:
            print("ERROR, something went wrong")

    # hosts_with_roles is list of [{"id": <host_id>, "role" : master}]
    def set_hosts_roles(self, cluster_id, hosts_with_roles):
        print("Setting roles for hosts", hosts_with_roles, "in cluster", cluster_id)
        hosts = {"hostsRoles": hosts_with_roles}
        result = requests.patch(self.cluster_url + cluster_id, json=hosts)
        result.raise_for_status()
        return result.json()
