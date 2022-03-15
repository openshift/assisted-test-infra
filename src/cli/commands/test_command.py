import os
import re
import subprocess
import uuid
from copy import deepcopy

import pytest
from prompt_toolkit.completion import Completer, NestedCompleter

from service_client import log

from .command import Command


class TestCommand(Command):
    """Command for execution a pytest test"""

    @classmethod
    def get_completer(cls) -> Completer:
        """Complete all pytest available tests"""
        proc = subprocess.Popen(
            ["python3", "-m", "pytest", "--collect-only", "-q"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, _stderr = proc.communicate()

        pattern = r"((?P<file>src/tests/.*\.py)::(?P<class>.*)::(?P<func>.*))"
        groups = [
            match.groupdict() for match in [re.match(pattern, line) for line in stdout.decode().split("\n")] if match
        ]

        # Split pytest function and files. Note that if for a certain test is decorated with pytest.parameterized
        # the function will have a different pattern (e.g. test_function[arg_value])
        groups_set = set((group["file"], group.get("func", "").split("[")[0]) for group in groups)

        test_options = {}
        for file, func in groups_set:
            if file not in test_options:
                test_options[file] = {}

            test_options[file][func] = None

        return NestedCompleter.from_nested_dict({"test": test_options})

    def handle(self):
        if not self._text:
            return

        original_environ = deepcopy(os.environ)
        try:
            for arg_str in self._args:
                var = re.match(r"(?P<key>.*)=(?P<value>.*)", arg_str).groupdict()
                os.environ[var["key"]] = var["value"]

            command = self._text.split(" ")
            _command, file, func, *_ = [var for var in command if var]
            junit_report_path = f"unittest_{str(uuid.uuid4())[:8]}.xml"
            log.setLevel(self._log_default_level)
            pytest.main([file, "-k", func, "--verbose", "-s", f"--junit-xml={junit_report_path}"])

        except BaseException:
            """Ignore any exception that might happen during test execution"""

        finally:
            from tests.config import reset_global_variables

            os.environ.clear()
            os.environ.update(original_environ)
            reset_global_variables()  # reset the config to its default state
