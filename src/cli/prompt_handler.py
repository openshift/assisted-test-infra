import logging
from typing import Union

from prompt_toolkit import prompt
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer
from prompt_toolkit.history import FileHistory
from prompt_toolkit.shortcuts import CompleteStyle, yes_no_dialog

from cli.commands.commands_factory import CommandFactory
from cli.commands.test_command import TestCommand
from cli.key_binding import bindings
from service_client import log
from tests.global_variables import DefaultVariables


class PromptHandler:
    def __init__(self, global_variables: DefaultVariables):
        self._global_variables = global_variables
        log.setLevel(logging.ERROR)

    @classmethod
    def _input(
        cls,
        prompt_text: str,
        completer: Completer,
        hint: str = " Control + Q for exit  |  Control + C for clear",
        history_file=None,
    ) -> Union[str, None]:

        history_args = {}
        if history_file:
            history_args["history"] = FileHistory(history_file)
            history_args["auto_suggest"] = AutoSuggestFromHistory()
            history_args["enable_history_search"] = True

        try:
            text = prompt(
                f"{prompt_text}> ",
                key_bindings=bindings,
                completer=completer,
                complete_style=CompleteStyle.COLUMN,
                bottom_toolbar=hint,
                **history_args,
            )
        except EOFError:
            return None

        return text

    def _get_environment_variables(self) -> Union[str, None]:
        args = ""
        result = yes_no_dialog(title="Environment Variables", text="Do you want to enter environment variables?").run()

        if result:
            args = self._input("└──── envs", completer=CommandFactory.env_vars_completers(self._global_variables))
            if args is None:
                return None

        return args

    def get_prompt_results(self):
        text = self._input("test-infra", completer=CommandFactory.get_completers(), history_file=".cli.history")
        if text is None:
            return None

        command = CommandFactory.get_command(text)
        if isinstance(command, TestCommand):
            if (args := self._get_environment_variables()) is None:
                return command
            command.args = args

        return command
