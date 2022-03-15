from abc import ABC, abstractmethod

from prompt_toolkit.completion import DummyCompleter

from service_client import log


class Command(ABC):
    """Define a command handler"""

    _log_default_level = log.level

    def __init__(self, text: str):
        self._text = text
        self._args = None

    @property
    def text(self):
        return self._text

    @property
    def args(self):
        return self._args

    @args.setter
    def args(self, args: str):
        self._args = [arg for arg in args.split(" ") if arg] if args else []

    @classmethod
    @abstractmethod
    def get_completer(cls):
        pass

    @abstractmethod
    def handle(self):
        pass


class DummyCommand(Command):
    """Dummy command handler - Prevent getting None command on cases where command test is empty"""

    @classmethod
    def get_completer(cls):
        return DummyCompleter()

    def handle(self):
        pass
