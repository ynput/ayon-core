from enum import Enum


class StrEnum(str, Enum):
    """A string-based Enum class that allows for string comparison."""

    def __str__(self) -> str:
        return self.value
