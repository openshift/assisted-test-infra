from prompt_toolkit.completion import NestedCompleter
from prompt_toolkit.shortcuts import message_dialog
from tabulate import tabulate

from .command import Command


class HelpCommand(Command):
    HELP_COMMAND = "help"

    @classmethod
    def get_completer(cls):
        return NestedCompleter.from_nested_dict({cls.HELP_COMMAND: None})

    def handle(self):
        headers = ("", "Key", "Single Press", "Double Press")
        keys = [
            ("1", "Control + C", "Clear the text if exist else exit the cli"),
            ("2", "Control + Q", "Exit the cli"),
            ("3", "Tab", "Enter and navigate the autocomplete menu"),
            ("4", "Right", "Step right or autocomplete from history"),
        ]
        table = tabulate(keys, headers=headers, tablefmt="fancy_grid")

        message_dialog(title="Help", text=str(table)).run()
