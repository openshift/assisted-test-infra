import logging
from test_infra.utils import run_command

#
# Create NAT rules networks that are nat using libvirt "nat" forwarding - which is currently none platform
# The logic behind it is to mark packets that are coming from libvirt bridges (i.e input_interfaces), and
# reference this mark in order to perform NAT operation on these packets.
#
class NatController:
    # Build iptables mark
    def _build_mark(self, ns_index):
        return 555 + int(ns_index)

    # Find all interfaces that have default route on them.  Usually it is a single interface.
    def _get_default_interfaces(self):
        interfaces, _, _ = run_command(r"ip -4 route | egrep '^default ' | awk '{print $5}'", shell=True)
        return set(interfaces.strip().split())

    # Mark all packets coming from the input_interface with "555".  Marking is needed because input interface
    # query is not available in POSTROUTING chain
    def _build_mark_string(self, input_interface, mark):
        rule_template = ["PREROUTING", "-i", input_interface, "-j", "MARK", "--set-mark", f"{mark}"]

        return " ".join(rule_template)

    # Perform MASQUERADE nat operation  on all marked packets with "555" and their output interface is "output_interface"
    def _build_nat_string(self, output_interface, mark):
        rule_template = ["POSTROUTING", "-m", "mark", "--mark", f"{mark}", "-o", output_interface, "-j", "MASQUERADE"]

        return " ".join(rule_template)

    # Build iptables command
    def _build_rule_string(self, option, rule_suffix):
        rule_template = ["iptables", "-t", "nat",  f"--{option}", rule_suffix]

        return " ".join(rule_template)

    # Check if rule exists
    def _does_rule_exist(self, rule_suffix):
        check_rule = self._build_rule_string('check', rule_suffix)
        _, _, exit_code = run_command(check_rule, shell=True, raise_errors=False)

        return exit_code == 0

    # Insert a new rule
    def _insert_rule(self, rule_suffix):
        insert_rule = self._build_rule_string('insert', rule_suffix)
        logging.info("Adding rule \"%s\"", insert_rule)
        run_command(insert_rule, shell=True)

    # Insert a new rule
    def _delete_rule(self, rule_suffix):
        delete_rule = self._build_rule_string('delete', rule_suffix)
        logging.info("Delete rule \"%s\"", delete_rule)
        run_command(delete_rule, shell=True)

    # Add a new rule if it doesn't already exist
    def _add_rule(self, rule_suffix):
        if not self._does_rule_exist(rule_suffix):
            self._insert_rule(rule_suffix)

    # Add a new rule if it doesn't already exist
    def _remove_rule(self, rule_suffix):
        if self._does_rule_exist(rule_suffix):
            self._delete_rule(rule_suffix)

    # Add rules for the input interfaces and output interfaces
    def add_nat_rules(self, input_interfaces, ns_index):
        logging.info("Adding nat rules for interfaces %s", input_interfaces)
        mark = self._build_mark(ns_index)
        for output_interface in self._get_default_interfaces():
            self._add_rule(self._build_nat_string(output_interface, mark))
        for input_interface in input_interfaces:
            self._add_rule(self._build_mark_string(input_interface, mark))

    # Delete nat rules
    def remove_nat_rules(self, input_interfaces, ns_index):
        logging.info("Deleting nat rules for interfaces %s", input_interfaces)
        mark = self._build_mark(ns_index)
        for input_interface in input_interfaces:
            self._remove_rule(self._build_mark_string(input_interface, mark))
        for output_interface in self._get_default_interfaces():
            self._remove_rule(self._build_nat_string(output_interface, mark))
