import abc
import contextlib

from kubernetes.client.rest import ApiException

from .common import KubeAPIContext, ObjectReference


class BaseResource(abc.ABC):
    """
    A base object of both custom resources and kubernetes resources that holds
    a shared KubeAPIContext. Any sub instance of this class will be added to the
    shared context.
    """

    context = KubeAPIContext()

    def __init__(self, name: str, namespace: str):
        self.context.resources.add(self)
        self._reference = ObjectReference(name=name, namespace=namespace)

    @property
    def ref(self) -> ObjectReference:
        return self._reference

    @abc.abstractmethod
    def create(self, **kwargs) -> None:
        pass

    @abc.abstractmethod
    def delete(self) -> None:
        pass

    @abc.abstractmethod
    def get(self) -> dict:
        pass

    def apply(self, **kwargs):
        with contextlib.suppress(ApiException):
            self.delete()

        self.create(**kwargs)


class BaseCustomResource(BaseResource):
    """
    Base class for all CRDs, enforces basic methods that every resource must
    have e.g create, path, get, delete and status.
    """

    @abc.abstractmethod
    def patch(self, **kwargs) -> None:
        pass

    @abc.abstractmethod
    def status(self, **kwargs) -> dict:
        pass
