from ayon_core.lib import StrEnum


class ContextChangeReason(StrEnum):
    """Reasons for context change in the host."""
    undefined = "undefined"
    workfile_open = "workfile.opened"
    workfile_save = "workfile.saved"
