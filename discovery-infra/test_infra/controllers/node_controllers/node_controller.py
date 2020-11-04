from typing import Dict, List
from test_infra.controllers.node_controllers import node


class NodeController:
    def list_nodes(self) -> Dict[str, node.Node]:
        raise NotImplementedError

    def shutdown_node(self, node_name: str) -> None:
        raise NotImplementedError

    def shutdown_all_nodes(self) -> None:
        raise NotImplementedError

    def start_node(self, node_name: str) -> None:
        raise NotImplementedError

    def start_all_nodes(self) -> List[node.Node]:
        raise NotImplementedError

    def restart_node(self, node_name: str) -> None:
        raise NotImplementedError
    
    def format_node_disk(self, node_name: str) -> None:
        raise NotImplementedError

    def format_all_node_disks(self) -> None:
        raise NotImplementedError

    def add_disk(self, node_name: str, size: str) -> None:
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

    def set_correct_boot_order_to_all_nodes(self) -> None:
        raise NotImplementedError
