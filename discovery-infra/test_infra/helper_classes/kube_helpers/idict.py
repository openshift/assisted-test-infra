from abc import ABC, abstractmethod


class IDict(ABC):
    def __repr__(self):
        return str(self.as_dict())

    @abstractmethod
    def as_dict(self) -> dict:
        pass
