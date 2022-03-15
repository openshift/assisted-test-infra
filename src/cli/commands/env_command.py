from prompt_toolkit.completion import NestedCompleter
from prompt_toolkit.shortcuts import clear
from tabulate import tabulate

from .. import cli_utils
from .command import Command


class EnvCommand(Command):
    """Get external environment information. Currently support only single command for listing clusters and clear
    the screen."""

    ENV_COMMAND_CLUSTERS = "clusters"
    ENV_COMMAND_LIST = "list"
    ENV_COMMAND_CLEAR = "clear"

    @classmethod
    def get_completer(cls):
        return NestedCompleter.from_nested_dict({cls.ENV_COMMAND_CLEAR: None, cls.ENV_COMMAND_LIST: {"clusters": None}})

    def command_list(self):
        if self.args and self.args[0] == "clusters":
            clusters = cli_utils.inventory_client().clusters_list()
            clusters_data = [(f"{i + 1})", clusters[i]["id"], clusters[i]["name"]) for i in range(len(clusters))]

            table = tabulate(clusters_data, headers=["", "Cluster ID", "Name"], tablefmt="fancy_grid")
            print(table, "\n")

    def handle(self):
        command, *args = self.text.strip().split(" ")
        self._args = args

        if command == self.ENV_COMMAND_CLEAR:
            clear()

        elif command == self.ENV_COMMAND_LIST:
            self.command_list()
