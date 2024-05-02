import warnings

from ayon_core.lib import CacheItem as _CacheItem
from ayon_core.lib import NestedCacheItem as _NestedCacheItem


# Cache classes were moved to `ayon_core.lib.cache`
class CacheItem(_CacheItem):
    def __init__(self, *args, **kwargs):
        warnings.warn(
            "Used 'CacheItem' from deprecated location "
            "'ayon_core.tools.common_models', use 'ayon_core.lib' instead.",
            DeprecationWarning,
        )
        super().__init__(*args, **kwargs)


class NestedCacheItem(_NestedCacheItem):
    def __init__(self, *args, **kwargs):
        warnings.warn(
            "Used 'NestedCacheItem' from deprecated location "
            "'ayon_core.tools.common_models', use 'ayon_core.lib' instead.",
            DeprecationWarning,
        )
        super().__init__(*args, **kwargs)


__all__ = (
    "CacheItem",
    "NestedCacheItem",
)
