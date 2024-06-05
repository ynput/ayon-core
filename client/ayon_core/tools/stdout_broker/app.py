import warnings
from .broker import StdOutBroker

warnings.warn(
    (
        "Import of 'StdOutBroker' from 'ayon_core.tools.stdout_broker.app'"
        " is deprecated. Please use 'ayon_core.tools.stdout_broker' instead."
    ),
    DeprecationWarning
)

__all__ = ("StdOutBroker", )
