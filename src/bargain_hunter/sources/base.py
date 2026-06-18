"""Source adapter interface. Each source normalises its feed into Deal objects."""

from abc import ABC, abstractmethod

from ..models import Deal


class Source(ABC):
    """A pluggable deal source."""

    name: str

    @abstractmethod
    def fetch(self) -> list[Deal]:
        """Return the deals currently visible from this source."""
        ...
