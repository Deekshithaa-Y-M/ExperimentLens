"""Compatibility helpers for the declared Python support range."""

from enum import Enum


class StrEnum(str, Enum):
    """String enum with consistent serialization on Python 3.10 through 3.12."""

    def __str__(self) -> str:
        return str(self.value)
