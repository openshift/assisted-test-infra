import logging
import re
from typing import Tuple, Union

from test_infra.controllers.iptables import IpTableCommandOption
from test_infra.utils import run_command, List


class NatController:
    """
    Create NAT rules networks that are nat using libvirt "nat" forwarding - which is currently none platform
    The logic behind it is to mark packets that are coming from libvirt bridges (i.e input_interfaces), and
    reference this mark in order to perform NAT operation on these packets.
    """
    def __init__(self, input_interfaces: Union[List, Tuple], ns_index: Union[str, int, None] = None):
        self._input_interfaces = input_interfaces
        self._ns_index = ns_index if ns_index is not None else self.get_namespace_index(input_interfaces[0])
        self._mark = self._build_mark()

    def add_nat_rules(self) -> None:
        """" Add rules for the input interfaces and output interfaces """
        logging.info("Adding nat rules for interfaces %s", self._input_interfaces)

        for output_interface in self._get_default_interfaces():
            self._add_rule(self._build_nat_string(output_interface))
        for input_interface in self._input_interfaces:
            self._add_rule(self._build_mark_string(input_interface))

    def remove_nat_rules(self) -> None:
        """  Delete nat rules """
        logging.info("Deleting nat rules for interfaces %s", self._input_interfaces)

        for input_interface in self._input_interfaces:
            self._remove_rule(self._build_mark_string(input_interface))
        for output_interface in self._get_default_interfaces():
            self._remove_rule(self._build_nat_string(output_interface))

    @classmethod
    def get_namespace_index(cls, libvirt_network_if):
        """ Hack to retrieve namespace index - does not exist in tests """
        matcher = re.match(r'^tt(\d+)$', libvirt_network_if)
        return int(matcher.groups()[0]) if matcher is not None else 0

    def _build_mark(self) -> int:
        """ Build iptables mark """
        return 555 + int(self._ns_index)

    @staticmethod
    def _get_default_interfaces() -> set:
        """ Find all interfaces that have default route on them.  Usually it is a single interface. """
        interfaces, _, _ = run_command(r"ip -4 route | egrep '^default ' | awk '{print $5}'", shell=True)
        return set(interfaces.strip().split())

    def _build_mark_string(self, input_interface):
        """Mark all packets coming from the input_interface with "555".  Marking is needed because input interface
        query is not available in POSTROUTING chain"""
        rule_template = ["PREROUTING", "-i", input_interface, "-j", "MARK", "--set-mark", f"{self._mark}"]

        return " ".join(rule_template)

    def _build_nat_string(self, output_interface: str) -> str:
        """Perform MASQUERADE nat operation  on all marked packets with "555" and their output interface
        is 'output_interface'"""
        rule_template = ["POSTROUTING", "-m", "mark", "--mark", f"{self._mark}", "-o", output_interface, "-j", "MASQUERADE"]

        return " ".join(rule_template)

    @staticmethod
    def _build_rule_string(option: IpTableCommandOption, rule_suffix: str) -> str:
        """ Build iptables command """
        rule_template = ["iptables", "-t", "nat", f"--{option.value}", rule_suffix]

        return " ".join(rule_template)

    @classmethod
    def _does_rule_exist(cls, rule_suffix: str) -> str:
        """ Check if rule exists """
        check_rule = cls._build_rule_string(IpTableCommandOption.CHECK, rule_suffix)
        _, _, exit_code = run_command(check_rule, shell=True, raise_errors=False)

        return exit_code == 0

    @classmethod
    def _insert_rule(cls, rule_suffix: str) -> None:
        """ Insert a new rule """
        insert_rule = cls._build_rule_string(IpTableCommandOption.INSERT, rule_suffix)
        logging.info('Adding rule "%s"', insert_rule)
        run_command(insert_rule, shell=True)

    @classmethod
    def _delete_rule(cls, rule_suffix: str) -> None:
        """ Insert a new rule """
        delete_rule = cls._build_rule_string(IpTableCommandOption.DELETE, rule_suffix)
        logging.info('Delete rule "%s"', delete_rule)
        run_command(delete_rule, shell=True)

    @classmethod
    def _add_rule(cls, rule_suffix: str) -> None:
        """ Add a new rule if it doesn't already exist """
        if not cls._does_rule_exist(rule_suffix):
            cls._insert_rule(rule_suffix)

    @classmethod
    def _remove_rule(cls, rule_suffix: str) -> None:
        """ Add a new rule if it doesn't already exist """
        if cls._does_rule_exist(rule_suffix):
            cls._delete_rule(rule_suffix)
