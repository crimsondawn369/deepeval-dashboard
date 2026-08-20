from abc import ABC, abstractmethod


class AppConnector(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def display_name(self) -> str: ...

    @abstractmethod
    def query(self, question: str) -> tuple[str, list]: ...
