# -*- coding: utf-8 -*-
import logging

from test_infra.utils import run_command


class IptableRule:
    def __init__(
        self, chain, target, protocol, dest_port="", sources=None, extra_args=""
    ):
        self._chain = chain
        self._target = target
        self._protocol = protocol
        self._dest_port = dest_port
        self._sources = sources if sources else []
        self._extra_args = extra_args

    def _build_command_string(self, option):
        sources_string = ",".join(self._sources)
        rule_template = [
            "iptables",
            f"--{option}",
            self._chain,
            "-p",
            self._protocol,
            "-j",
            self._target,
        ]

        if self._sources:
            rule_template += ["-s", sources_string]

        if self._dest_port:
            rule_template += ["--dport", self._dest_port]

        if self._extra_args:
            rule_template += [self._extra_args]

        return " ".join(rule_template)

    def _does_rule_exist(self):
        check_rule = self._build_command_string("check")
        _, _, exit_code = run_command(check_rule, shell=True, raise_errors=False)

        return exit_code == 0

    def add_sources(self, sources):
        self._sources += sources

    def insert(self):
        if not self._does_rule_exist():
            insert_rule = self._build_command_string("insert")
            logging.info(f"Setting iptable rule: {insert_rule}")
            run_command(insert_rule, shell=True)

    def delete(self):
        if self._does_rule_exist():
            delete_rule = self._build_command_string("delete")
            logging.info(f"Removing iptable rule: {delete_rule}")
            run_command(delete_rule, shell=True)
