from enum import Enum


class StrEnum(str, Enum):
    """A string-based Enum class that allows for string comparison."""

    def __str__(self) -> str:
        return self.value


class ContextChangeReason(StrEnum):
    """Reasons for context change in the host."""
    undefined = "undefined"
    workfile_open = "workfile.opened"
    workfile_save = "workfile.saved"
