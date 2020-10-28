from typing import Dict, List
from test_infra.controllers.node_controllers import host


class NodeController:
    def list_nodes(self) -> Dict[str, host.Host]:
        raise NotImplementedError

    def shutdown_node(self, node_name: str) -> None:
        raise NotImplementedError

    def shutdown_all_nodes(self) -> None:
        raise NotImplementedError

    def start_node(self, node_name: str) -> None:
        raise NotImplementedError

    def start_all_nodes(self) -> List[host.Host]:
        raise NotImplementedError

    def restart_node(self, node_name: str) -> None:
        raise NotImplementedError
    
    def format_node_disk(self, node_name: str) -> None:
        raise NotImplementedError

    def format_all_node_disks(self) -> None:
        raise NotImplementedError

    def get_ingress_and_api_vips(self) -> dict:
        raise NotImplementedError

    def destroy_all_nodes(self) -> None:
        raise NotImplementedError

    def prepare_nodes(self):
        pass

    def is_active(self, node_name) -> bool:
        raise NotImplementedError

    def set_boot_order(self, node_name, cd_first=False) -> None:
        raise NotImplementedError
