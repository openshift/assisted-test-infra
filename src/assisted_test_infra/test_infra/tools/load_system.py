from abc import ABC, abstractmethod
from string import Template

from service_client import log


class Command(ABC):
    base_command = None
    redirect = " > /dev/null &"

    def __init__(self, nodes: list):
        """Initialize node_undo dict, keys are node object
        :param nodes: node is the command receiver  run_command
        """
        self.node_undo_commands = dict()
        self._nodes = nodes

    @property
    def receivers(self):
        # check if nodes exist and active before running command
        active_nodes = []
        for node in self._nodes:
            if self._verify_node_active(node):
                active_nodes.append(node)
        return active_nodes

    @staticmethod
    def _verify_node_active(node):
        if node and node.is_active:
            return node
        log.info(f"Node {node.name} not active anymore")
        return None

    @abstractmethod
    def execute(self):
        pass

    def undo(self):
        for node in self.receivers:
            cmd = self.node_undo_commands[node]
            log.info(f"{node.name}  background execute: {cmd}")
            node.run_command(cmd, background=True)


class LoadCPU(Command):
    """Load cpu command
    The command replicated per cpu core and causes to high cpu usage.
    In order to increase cpu load we can increase the core_numbers
    example: in case we have 4 core we can run pipes and use more
    command :
    # cat /dev/urandom | gzip -9 | gzip -d | gzip -9 | gzip -d > /dev/null
    The base command can be sha512sum /dev/urandom
    """

    base_command = "while true ; do echo; done"

    def __init__(self, nodes, core_numbers: int):
        super().__init__(nodes)
        self.core_numbers = core_numbers

    def execute(self):
        cores_dup = "| gzip -9" * self.core_numbers
        command = f"{self.base_command} {cores_dup} {self.redirect}"
        for node in self.receivers:
            log.info(f"{node.name}  background execute: {command}")
            node.run_command(command, background=True)
            self.node_undo_commands[node] = "kill `pidof gzip`"


class LoadRam(Command):
    """Load increase RAM memory by giga param
    mount to ramfs and copy data to the ram storage and increasing ram usage.
    """

    base_command = Template(
        """mkdir $folder;
        mount -t ramfs ramfs $folder/;
        dd if=/dev/zero of=$folder/file bs=1G count=$ram_giga;
        """
    )

    def __init__(self, nodes, ram_giga: int, folder="ram123"):
        super().__init__(nodes)
        self.ram_giga = ram_giga
        self.folder = folder

    def execute(self):
        command = self.base_command.safe_substitute(ram_giga=self.ram_giga, folder=self.folder)
        command = f"{command} {self.redirect}"
        for node in self.receivers:
            log.info(f"{node.name}  background execute: {command}")
            node.run_command(command, background=True)
            self.node_undo_commands[node] = "umount ram123/; rm -rf ram123"


class LoadNetworkUpload(Command):
    """Load network usage by limiting bandwidth traffic,
    Limit bandwidth per interface, simulate slow network.
    sudo tc qdisc add dev ens3 root tbf rate 50kbit latency 50ms  burst 1540
    """

    base_command = Template("sudo tc qdisc $action dev $interface root tbf rate $rate_limit latency 50ms burst 1540")

    def __init__(self, nodes, rate_limit: str, interface: str, action="add"):
        super().__init__(nodes)
        self.interface = interface
        self.rate_limit = rate_limit
        self.action = action

    def execute(self):
        command = self.base_command.safe_substitute(
            action=self.action, interface=self.interface, rate_limit=self.rate_limit
        )
        for node in self.receivers:
            log.info(f"{node.name}  background execute: {command}")
            node.run_command(command, background=True)
            self.node_undo_commands[node] = command.replace("add", "del")


class LoadNetworkDownload(Command):
    """Load network usage by limiting download bandwidth traffic (ingress),
    Limit bandwidth per interface, simulate slow network.
    sudo modprobe ifb
    sudo ip link add name ifb0 type ifb 2> /dev/null
    sudo ip link set dev ifb0 up

    sudo tc qdisc add dev ifb0 root handle 1: htb r2q 1
    sudo tc class add dev ifb0 parent 1: classid 1:1 htb rate $SPEED
    sudo tc filter add dev ifb0 parent 1: matchall flowid 1:1

    sudo tc qdisc add dev ens3 ingress
    sudo tc filter add dev ens3 ingress matchall action mirred egress redirect dev ifb0

    ingress tc example:
    https://linux-man.org/2021/09/24/how-to-limit-ingress-bandwith-with-tc-command-in-linux/
    """

    base_command = Template(
        """sudo ip link $action name ifb0 type ifb 2> /dev/null;
        sudo ip link set dev ifb0 up;
        sudo tc qdisc $action dev ifb0 root handle 1: htb r2q 1;
        sudo tc class $action dev ifb0 parent 1: classid 1:1 htb rate $rate_limit;
        sudo tc filter $action dev ifb0 parent 1: matchall flowid 1:1;
        sudo tc qdisc $action dev $interface ingress;
        sudo tc filter $action dev $interface ingress matchall action mirred egress redirect dev ifb0;
        """
    )

    def __init__(self, nodes, rate_limit: str, interface: str, action="add"):
        super().__init__(nodes)
        self.interface = interface
        self.rate_limit = rate_limit
        self.action = action

    def execute(self):
        command = self.base_command.safe_substitute(
            action=self.action, interface=self.interface, rate_limit=self.rate_limit
        )
        for node in self.receivers:
            log.info(f"{node.name}  background execute: {command}")
            node.run_command(command, background=True)

            self.node_undo_commands[node] = f"sudo tc qdisc del dev {self.interface} ingress"
