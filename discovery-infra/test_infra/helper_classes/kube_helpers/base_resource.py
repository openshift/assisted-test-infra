import abc

from .common import ObjectReference


class BaseCustomResource(abc.ABC):
    """
    Base class for all CRDs, enforces basic methods that every resource must
    have e.g create, path, get, delete and status.
    """

    def __init__(self, name: str, namespace: str):
        self._reference = ObjectReference(name=name, namespace=namespace)

    @property
    def ref(self) -> ObjectReference:
        return self._reference

    @abc.abstractmethod
    def create(self, **kwargs) -> None:
        pass

    @abc.abstractmethod
    def patch(self, **kwargs) -> None:
        pass

    @abc.abstractmethod
    def get(self) -> dict:
        pass

    @abc.abstractmethod
    def delete(self) -> None:
        pass

    @abc.abstractmethod
    def status(self, **kwargs) -> dict:
        pass
