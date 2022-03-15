from prompt_toolkit.shortcuts import clear, message_dialog, set_title

from tests.global_variables import DefaultVariables

from .commands.command import DummyCommand
from .commands.commands_factory import InvalidCommandError
from .prompt_handler import PromptHandler


class CliApplication:
    def __init__(self):
        self._global_variables = DefaultVariables()
        self._prompt_handler = PromptHandler(self._global_variables)

    def _init_window(self):
        clear()
        set_title("Test Infra CLI")

        if not self._global_variables.pull_secret:
            message_dialog(
                title="Pull Secret", text="Cant find PULL_SECRET, some functionality might not work as expected"
            ).run()

    def run(self):
        self._init_window()
        while True:
            try:
                command = self._prompt_handler.get_prompt_results()
            except InvalidCommandError:
                print("\033[1;31mError, invalid command!\033[0m")
                continue
            if command is None:
                break
            if isinstance(command, DummyCommand):
                continue

            command.handle()

        print("Exiting ....")
