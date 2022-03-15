import functools
from typing import Union

from prompt_toolkit.completion import merge_completers

from tests.global_variables import DefaultVariables

from .. import cli_utils
from ..completers import DynamicNestedCompleter
from .command import Command, DummyCommand
from .env_command import EnvCommand
from .help_command import HelpCommand
from .test_command import TestCommand


class InvalidCommandError(Exception):
    pass


class CommandFactory:
    _supported_commands = {
        "": DummyCommand,
        "test": TestCommand,
        "list": EnvCommand,
        "clear": EnvCommand,
        "help": HelpCommand,
    }

    @classmethod
    def get_command(cls, text: str) -> Union[Command, None]:
        text = text if text else ""
        factory = cls._supported_commands.get(text.split(" ")[0])
        try:
            return factory(text)
        except TypeError as e:
            raise InvalidCommandError(f"Error, invalid command {text}") from e

    @classmethod
    @functools.cache
    def get_completers(cls):
        commands = [c.get_completer() for c in {cmd for k, cmd in cls._supported_commands.items() if k}]
        return merge_completers(commands)

    @classmethod
    def env_vars_completers(cls, global_variables: DefaultVariables):
        keys = cli_utils.get_env_args_keys()
        return DynamicNestedCompleter.from_nested_dict({k: None for k in keys}, global_variables=global_variables)
