import time
import collections

InitInfo = collections.namedtuple(
    "InitInfo",
    ["default_factory", "lifetime"]
)


def _default_factory_func():
    return None


class CacheItem:
    """Simple cache item with lifetime and default factory for default value.

    Default factory should return default value that is used on init
        and on reset.

    Args:
        default_factory (Optional[callable]): Function that returns default
            value used on init and on reset.
        lifetime (Optional[int]): Lifetime of the cache data in seconds.
            Default lifetime is 120 seconds.

    """
    def __init__(self, default_factory=None, lifetime=None):
        if lifetime is None:
            lifetime = 120
        self._lifetime = lifetime
        self._last_update = None
        if default_factory is None:
            default_factory = _default_factory_func
        self._default_factory = default_factory
        self._data = default_factory()

    @property
    def is_valid(self):
        """Is cache valid to use.

        Return:
            bool: True if cache is valid, False otherwise.

        """
        if self._last_update is None:
            return False

        return (time.time() - self._last_update) < self._lifetime

    def set_lifetime(self, lifetime):
        """Change lifetime of cache item.

        Args:
            lifetime (int): Lifetime of the cache data in seconds.
        """

        self._lifetime = lifetime

    def set_invalid(self):
        """Set cache as invalid."""

        self._last_update = None

    def reset(self):
        """Set cache as invalid and reset data."""

        self._last_update = None
        self._data = self._default_factory()

    def get_data(self):
        """Receive cached data.

        Returns:
            Any: Any data that are cached.

        """
        return self._data

    def update_data(self, data):
        """Update cache data.

        Args:
            data (Any): Any data that are cached.

        """
        self._data = data
        self._last_update = time.time()


class NestedCacheItem:
    """Helper for cached items stored in nested structure.

    Example:
        >>> cache = NestedCacheItem(levels=2, default_factory=lambda: 0)
        >>> cache["a"]["b"].is_valid
        False
        >>> cache["a"]["b"].get_data()
        0
        >>> cache["a"]["b"] = 1
        >>> cache["a"]["b"].is_valid
        True
        >>> cache["a"]["b"].get_data()
        1
        >>> cache.reset()
        >>> cache["a"]["b"].is_valid
        False

    Args:
        levels (int): Number of nested levels where read cache is stored.
        default_factory (Optional[callable]): Function that returns default
            value used on init and on reset.
        lifetime (Optional[int]): Lifetime of the cache data in seconds.
            Default value is based on default value of 'CacheItem'.
        _init_info (Optional[InitInfo]): Private argument. Init info for
            nested cache where created from parent item.

    """
    def __init__(
        self, levels=1, default_factory=None, lifetime=None, _init_info=None
    ):
        if levels < 1:
            raise ValueError("Nested levels must be greater than 0")
        self._data_by_key = {}
        if _init_info is None:
            _init_info = InitInfo(default_factory, lifetime)
        self._init_info = _init_info
        self._levels = levels

    def __getitem__(self, key):
        """Get cached data.

        Args:
            key (str): Key of the cache item.

        Returns:
            Union[NestedCacheItem, CacheItem]: Cache item.

        """
        cache = self._data_by_key.get(key)
        if cache is None:
            if self._levels > 1:
                cache = NestedCacheItem(
                    levels=self._levels - 1,
                    _init_info=self._init_info
                )
            else:
                cache = CacheItem(
                    self._init_info.default_factory,
                    self._init_info.lifetime
                )
            self._data_by_key[key] = cache
        return cache

    def __setitem__(self, key, value):
        """Update cached data.

        Args:
            key (str): Key of the cache item.
            value (Any): Any data that are cached.

        """
        if self._levels > 1:
            raise AttributeError((
                "{} does not support '__setitem__'. Lower nested level by {}"
            ).format(self.__class__.__name__, self._levels - 1))
        cache = self[key]
        cache.update_data(value)

    def get(self, key):
        """Get cached data.

        Args:
            key (str): Key of the cache item.

        Returns:
            Union[NestedCacheItem, CacheItem]: Cache item.

        """
        return self[key]

    def cached_count(self):
        """Amount of cached items.

        Returns:
            int: Amount of cached items.

        """
        return len(self._data_by_key)

    def clear_key(self, key):
        """Clear cached item by key.

        Args:
            key (str): Key of the cache item.

        """
        self._data_by_key.pop(key, None)

    def clear_invalid(self):
        """Clear all invalid cache items.

        Note:
            To clear all cache items use 'reset'.

        """
        changed = {}
        children_are_nested = self._levels > 1
        for key, cache in tuple(self._data_by_key.items()):
            if children_are_nested:
                output = cache.clear_invalid()
                if output:
                    changed[key] = output
                if not cache.cached_count():
                    self._data_by_key.pop(key)
            elif not cache.is_valid:
                changed[key] = cache.get_data()
                self._data_by_key.pop(key)
        return changed

    def reset(self):
        """Reset cache.

        Note:
            To clear only invalid cache items use 'clear_invalid'.

        """
        self._data_by_key = {}

    def set_lifetime(self, lifetime):
        """Change lifetime of all children cache items.

        Args:
            lifetime (int): Lifetime of the cache data in seconds.

        """
        self._init_info.lifetime = lifetime
        for cache in self._data_by_key.values():
            cache.set_lifetime(lifetime)

    @property
    def is_valid(self):
        """Raise reasonable error when called on wrong level.

        Raises:
            AttributeError: If called on nested cache item.

        """
        raise AttributeError((
            "{} does not support 'is_valid'. Lower nested level by '{}'"
        ).format(self.__class__.__name__, self._levels))
