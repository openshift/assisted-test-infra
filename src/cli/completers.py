import os
import re
import subprocess
from typing import Dict, Optional, Union

from prompt_toolkit.completion import Completer, NestedCompleter, PathCompleter, WordCompleter
from prompt_toolkit.completion.nested import NestedDict
from prompt_toolkit.document import Document

from cli import cli_utils
from consts import DiskEncryptionMode, DiskEncryptionRoles, NetworkType
from tests.global_variables import DefaultVariables


class BooleanCompleter(WordCompleter):
    def __init__(self, **kwargs) -> None:
        super().__init__(["true", "false"], **kwargs)


class DynamicNestedCompleter(NestedCompleter):
    def __init__(self, options: Dict[str, Optional[Completer]], ignore_case: bool = True) -> None:
        super().__init__(options, ignore_case)
        self.path_completer = PathCompleter()
        self.boolean_completer = BooleanCompleter()

    @classmethod
    def from_nested_dict(cls, data: NestedDict, global_variables: DefaultVariables) -> "NestedCompleter":
        nested_completer = super().from_nested_dict(data)
        return nested_completer

    def get_dynamic_options(self, key: str) -> Union[Completer, None]:
        if key == "OPENSHIFT_VERSION":
            return WordCompleter(cli_utils.inventory_client().get_openshift_versions().keys())

        if key == "CLUSTER_ID":
            return WordCompleter([cluster["id"] for cluster in cli_utils.inventory_client().clusters_list()])

        if key == "NETWORK_TYPE":
            return WordCompleter([NetworkType.all()])

        if key == "DISK_ENCRYPTION_MODE":
            return WordCompleter([DiskEncryptionMode.all()])

        if key == "DISK_ENCRYPTION_ROLES":
            return WordCompleter([DiskEncryptionRoles.all()])

        if key == "NAMESPACE":
            return WordCompleter(cli_utils.get_namespace())

        if key in ["ISO", "ISO_DOWNLOAD_PATH", "STORAGE_POOL_PATH", "PRIVATE_KEY_PATH"]:
            return self.path_completer

        if key in cli_utils.get_boolean_keys():
            return self.boolean_completer

        return None

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.lstrip()
        separator_in_text = False

        separators = ["=", "/"]
        for sep in separators:
            if not text.endswith(sep):
                continue

            # Parse all arguments in current input string to List[Tuple[key, value]].
            # e,g: '<VARIABLE_A>=<value1> <VARIABLE_B>=<value2> <VARIABLE_C>= ....'
            args = re.findall(re.compile(r"([^\s=]+)=(.*?)(?=(?:\s[^\s=]+=|$))"), text)
            current_arg = args[-1][0]

            completer = self.get_dynamic_options(current_arg)
            # If we have a sub completer, use this for the completions.
            if completer is not None:
                separator_in_text = True
                remaining_text = args[-1][-1] if len(args) > 0 and len(args[-1]) > 0 else ""

                for c in completer.get_completions(Document(remaining_text), complete_event):
                    yield c
                break

        # No space in the input: behave exactly like `WordCompleter`.
        if not separator_in_text:
            completer = WordCompleter(list(self.options.keys()), ignore_case=self.ignore_case)
            for c in completer.get_completions(document, complete_event):
                yield c


class Completers:
    @classmethod
    def _makefile_targets_completers(cls, global_variables: DefaultVariables):
        cmd = "make -qp | awk -F':' '/^[a-zA-Z0-9][^$#\\t=]*:([^=]|$)/ {split($1,A,/ /);for(i in A)print A[i]}'"
        output = subprocess.check_output(cmd, shell=True, cwd=os.environ.get("ROOT_DIR", os.getcwd()))

        return DynamicNestedCompleter.from_nested_dict(
            {"make": {t: None for t in sorted([f"{w}" for w in output.decode().split("\n") if w and w != "Makefile"])}},
            global_variables=global_variables,
        )
