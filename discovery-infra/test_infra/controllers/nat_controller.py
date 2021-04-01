import logging
from test_infra.utils import run_command


class NatController:
    """
    Create NAT rules networks that are nat using libvirt "nat" forwarding - which is currently none platform
    The logic behind it is to mark packets that are coming from libvirt bridges (i.e input_interfaces), and
    reference this mark in order to perform NAT operation on these packets.
    """

    @staticmethod
    def _build_mark(ns_index):
        """ Build iptables mark """
        return 555 + int(ns_index)

    @staticmethod
    def _get_default_interfaces():
        """ Find all interfaces that have default route on them.  Usually it is a single interface. """
        interfaces, _, _ = run_command(r"ip -4 route | egrep '^default ' | awk '{print $5}'", shell=True)
        return set(interfaces.strip().split())

    @staticmethod
    def _build_mark_string(input_interface, mark):
        """ Mark all packets coming from the input_interface with "555".  Marking is needed because input interface
        query is not available in POSTROUTING chain """
        rule_template = ["PREROUTING", "-i", input_interface, "-j", "MARK", "--set-mark", f"{mark}"]

        return " ".join(rule_template)

    @staticmethod
    def _build_nat_string(output_interface, mark):
        """ Perform MASQUERADE nat operation  on all marked packets with "555" and their output interface
        is 'output_interface' """
        rule_template = ["POSTROUTING", "-m", "mark", "--mark", f"{mark}", "-o", output_interface, "-j", "MASQUERADE"]

        return " ".join(rule_template)

    @staticmethod
    def _build_rule_string(option, rule_suffix):
        """ Build iptables command """
        rule_template = ["iptables", "-t", "nat", f"--{option}", rule_suffix]

        return " ".join(rule_template)

    @classmethod
    def _does_rule_exist(cls, rule_suffix):
        """ Check if rule exists """
        check_rule = cls._build_rule_string('check', rule_suffix)
        _, _, exit_code = run_command(check_rule, shell=True, raise_errors=False)

        return exit_code == 0

    @classmethod
    def _insert_rule(cls, rule_suffix):
        """ Insert a new rule """
        insert_rule = cls._build_rule_string('insert', rule_suffix)
        logging.info("Adding rule \"%s\"", insert_rule)
        run_command(insert_rule, shell=True)

    @classmethod
    def _delete_rule(cls, rule_suffix):
        """ Insert a new rule """
        delete_rule = cls._build_rule_string('delete', rule_suffix)
        logging.info("Delete rule \"%s\"", delete_rule)
        run_command(delete_rule, shell=True)

    @classmethod
    def _add_rule(cls, rule_suffix):
        """ Add a new rule if it doesn't already exist """
        if not cls._does_rule_exist(rule_suffix):
            cls._insert_rule(rule_suffix)

    @classmethod
    def _remove_rule(cls, rule_suffix):
        """ Add a new rule if it doesn't already exist """
        if cls._does_rule_exist(rule_suffix):
            cls._delete_rule(rule_suffix)

    @classmethod
    def add_nat_rules(cls, input_interfaces, ns_index):
        """" Add rules for the input interfaces and output interfaces """
        logging.info("Adding nat rules for interfaces %s", input_interfaces)
        mark = cls._build_mark(ns_index)
        for output_interface in cls._get_default_interfaces():
            cls._add_rule(cls._build_nat_string(output_interface, mark))
        for input_interface in input_interfaces:
            cls._add_rule(cls._build_mark_string(input_interface, mark))

    @classmethod
    def remove_nat_rules(cls, input_interfaces, ns_index):
        """  Delete nat rules """
        logging.info("Deleting nat rules for interfaces %s", input_interfaces)
        mark = cls._build_mark(ns_index)
        for input_interface in input_interfaces:
            cls._remove_rule(cls._build_mark_string(input_interface, mark))
        for output_interface in cls._get_default_interfaces():
            cls._remove_rule(cls._build_nat_string(output_interface, mark))
