import logging

from test_infra.controllers.node_controllers.libvirt_controller import LibvirtController


class QeVmController(LibvirtController):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def format_node_disk(self, node_name):
        logging.info("Formating disk for %s", node_name)
        self.format_disk(f'/var/lib/libvirt/images/linchpin/{node_name}.qcow2')

    def add_disk(self, node_name, size):
        logging.info("Add disk for %s", node_name)
        vol_path=f'/var/lib/libvirt/images/linchpin/{node_name}-second.qcow2'
        self.create_disk(vol_path=vol_path, size=size, pool_name="default")

    def get_ingress_and_api_vips(self):
        return {"api_vip": "192.168.123.5", "ingress_vip": "192.168.123.10"}

