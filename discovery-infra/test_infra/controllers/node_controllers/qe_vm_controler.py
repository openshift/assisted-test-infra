import logging
from test_infra import utils
from test_infra.controllers.node_controllers.libvirt_controller import LibvirtController


class QeVmController(LibvirtController):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def format_node_disk(self, node_name):
        logging.info("Formating disk for %s", node_name)
        command = f"qemu-img info /var/lib/libvirt/images/linchpin/{node_name}.qcow2 | grep 'virtual size'"
        output = utils.run_command(command, shell=True)        
        image_size = output[0].split(' ')[2]

        command = f'qemu-img create -f qcow2 /var/lib/libvirt/images/linchpin/{node_name}.qcow2 {image_size}'
        utils.run_command(command, shell=True)

    def get_ingress_and_api_vips(self):
        return {"api_vip": "192.168.123.5", "ingress_vip": "192.168.123.10"}
