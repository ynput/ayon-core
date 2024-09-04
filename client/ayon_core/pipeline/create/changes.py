import copy

_EMPTY_VALUE = object()


class TrackChangesItem:
    """Helper object to track changes in data.

    Has access to full old and new data and will create deep copy of them,
    so it is not needed to create copy before passed in.

    Can work as a dictionary if old or new value is a dictionary. In
    that case received object is another object of 'TrackChangesItem'.

    Goal is to be able to get old or new value as was or only changed values
    or get information about removed/changed keys, and all of that on
    any "dictionary level".

    ```
    # Example of possible usages
    >>> old_value = {
    ...     "key_1": "value_1",
    ...     "key_2": {
    ...         "key_sub_1": 1,
    ...         "key_sub_2": {
    ...             "enabled": True
    ...         }
    ...     },
    ...     "key_3": "value_2"
    ... }
    >>> new_value = {
    ...     "key_1": "value_1",
    ...     "key_2": {
    ...         "key_sub_2": {
    ...             "enabled": False
    ...         },
    ...         "key_sub_3": 3
    ...     },
    ...     "key_3": "value_3"
    ... }

    >>> changes = TrackChangesItem(old_value, new_value)
    >>> changes.changed
    True

    >>> changes["key_2"]["key_sub_1"].new_value is None
    True

    >>> list(sorted(changes.changed_keys))
    ['key_2', 'key_3']

    >>> changes["key_2"]["key_sub_2"]["enabled"].changed
    True

    >>> changes["key_2"].removed_keys
    {'key_sub_1'}

    >>> list(sorted(changes["key_2"].available_keys))
    ['key_sub_1', 'key_sub_2', 'key_sub_3']

    >>> changes.new_value == new_value
    True

    # Get only changed values
    only_changed_new_values = {
        key: changes[key].new_value
        for key in changes.changed_keys
    }
    ```

    Args:
        old_value (Any): Old value.
        new_value (Any): New value.
    """

    def __init__(self, old_value, new_value):
        self._changed = old_value != new_value
        # Resolve if value is '_EMPTY_VALUE' after comparison of the values
        if old_value is _EMPTY_VALUE:
            old_value = None
        if new_value is _EMPTY_VALUE:
            new_value = None
        self._old_value = copy.deepcopy(old_value)
        self._new_value = copy.deepcopy(new_value)

        self._old_is_dict = isinstance(old_value, dict)
        self._new_is_dict = isinstance(new_value, dict)

        self._old_keys = None
        self._new_keys = None
        self._available_keys = None
        self._removed_keys = None

        self._changed_keys = None

        self._sub_items = None

    def __getitem__(self, key):
        """Getter looks into subitems if object is dictionary."""

        if self._sub_items is None:
            self._prepare_sub_items()
        return self._sub_items[key]

    def __bool__(self):
        """Boolean of object is if old and new value are the same."""

        return self._changed

    def get(self, key, default=None):
        """Try to get sub item."""

        if self._sub_items is None:
            self._prepare_sub_items()
        return self._sub_items.get(key, default)

    @property
    def old_value(self):
        """Get copy of old value.

        Returns:
            Any: Whatever old value was.
        """

        return copy.deepcopy(self._old_value)

    @property
    def new_value(self):
        """Get copy of new value.

        Returns:
            Any: Whatever new value was.
        """

        return copy.deepcopy(self._new_value)

    @property
    def changed(self):
        """Value changed.

        Returns:
            bool: If data changed.
        """

        return self._changed

    @property
    def is_dict(self):
        """Object can be used as dictionary.

        Returns:
            bool: When can be used that way.
        """

        return self._old_is_dict or self._new_is_dict

    @property
    def changes(self):
        """Get changes in raw data.

        This method should be used only if 'is_dict' value is 'True'.

        Returns:
            Dict[str, Tuple[Any, Any]]: Changes are by key in tuple
                (<old value>, <new value>). If 'is_dict' is 'False' then
                output is always empty dictionary.
        """

        output = {}
        if not self.is_dict:
            return output

        old_value = self.old_value
        new_value = self.new_value
        for key in self.changed_keys:
            _old = None
            _new = None
            if self._old_is_dict:
                _old = old_value.get(key)
            if self._new_is_dict:
                _new = new_value.get(key)
            output[key] = (_old, _new)
        return output

    # Methods/properties that can be used when 'is_dict' is 'True'
    @property
    def old_keys(self):
        """Keys from old value.

        Empty set is returned if old value is not a dict.

        Returns:
            Set[str]: Keys from old value.
        """

        if self._old_keys is None:
            self._prepare_keys()
        return set(self._old_keys)

    @property
    def new_keys(self):
        """Keys from new value.

        Empty set is returned if old value is not a dict.

        Returns:
            Set[str]: Keys from new value.
        """

        if self._new_keys is None:
            self._prepare_keys()
        return set(self._new_keys)

    @property
    def changed_keys(self):
        """Keys that has changed from old to new value.

        Empty set is returned if both old and new value are not a dict.

        Returns:
            Set[str]: Keys of changed keys.
        """

        if self._changed_keys is None:
            self._prepare_sub_items()
        return set(self._changed_keys)

    @property
    def available_keys(self):
        """All keys that are available in old and new value.

        Empty set is returned if both old and new value are not a dict.
        Output is Union of 'old_keys' and 'new_keys'.

        Returns:
            Set[str]: All keys from old and new value.
        """

        if self._available_keys is None:
            self._prepare_keys()
        return set(self._available_keys)

    @property
    def removed_keys(self):
        """Key that are not available in new value but were in old value.

        Returns:
            Set[str]: All removed keys.
        """

        if self._removed_keys is None:
            self._prepare_sub_items()
        return set(self._removed_keys)

    def _prepare_keys(self):
        old_keys = set()
        new_keys = set()
        if self._old_is_dict and self._new_is_dict:
            old_keys = set(self._old_value.keys())
            new_keys = set(self._new_value.keys())

        elif self._old_is_dict:
            old_keys = set(self._old_value.keys())

        elif self._new_is_dict:
            new_keys = set(self._new_value.keys())

        self._old_keys = old_keys
        self._new_keys = new_keys
        self._available_keys = old_keys | new_keys
        self._removed_keys = old_keys - new_keys

    def _prepare_sub_items(self):
        sub_items = {}
        changed_keys = set()

        old_keys = self.old_keys
        new_keys = self.new_keys
        new_value = self.new_value
        old_value = self.old_value
        if self._old_is_dict and self._new_is_dict:
            for key in self.available_keys:
                item = TrackChangesItem(
                    old_value.get(key), new_value.get(key)
                )
                sub_items[key] = item
                if item.changed or key not in old_keys or key not in new_keys:
                    changed_keys.add(key)

        elif self._old_is_dict:
            old_keys = set(old_value.keys())
            available_keys = set(old_keys)
            changed_keys = set(available_keys)
            for key in available_keys:
                # NOTE Use '_EMPTY_VALUE' because old value could be 'None'
                #   which would result in "unchanged" item
                sub_items[key] = TrackChangesItem(
                    old_value.get(key), _EMPTY_VALUE
                )

        elif self._new_is_dict:
            new_keys = set(new_value.keys())
            available_keys = set(new_keys)
            changed_keys = set(available_keys)
            for key in available_keys:
                # NOTE Use '_EMPTY_VALUE' because new value could be 'None'
                #   which would result in "unchanged" item
                sub_items[key] = TrackChangesItem(
                    _EMPTY_VALUE, new_value.get(key)
                )

        self._sub_items = sub_items
        self._changed_keys = changed_keys
