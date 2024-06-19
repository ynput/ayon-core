import collections
import json
from typing import Optional, Union

from qtpy import QtGui

from .utils import get_icon_name_char

Position = collections.namedtuple("Offset", ["x", "y"])


class IconSubOption:
    def __init__(
        self,
        on_normal,
        on_disabled=None,
        on_active=None,
        on_selected=None,
        off_normal=None,
        off_disabled=None,
        off_active=None,
        off_selected=None,
    ):
        if off_normal is None:
            off_normal = on_normal

        if on_disabled is None:
            on_disabled = on_normal
        if off_disabled is None:
            off_disabled = on_disabled

        if on_active is None:
            on_active = on_normal
        if off_active is None:
            off_active = on_active

        if on_selected is None:
            on_selected = on_normal
        if off_selected is None:
            off_selected = on_selected

        self._identifier = None
        self.on_normal = on_normal
        self.on_disabled = on_disabled
        self.on_active = on_active
        self.on_selected = on_selected
        self.off_normal = off_normal
        self.off_disabled = off_disabled
        self.off_active = off_active
        self.off_selected = off_selected

    @property
    def identifier(self):
        if self._identifier is None:
            self._identifier = self._generate_identifier()
        return self._identifier

    def get_value_for_state(self, state, mode):
        if state == QtGui.QIcon.On:
            if mode == QtGui.QIcon.Disabled:
                return self.on_disabled
            if mode == QtGui.QIcon.Active:
                return self.on_active
            if mode == QtGui.QIcon.Selected:
                return self.on_selected
            return self.on_normal

        if mode == QtGui.QIcon.Disabled:
            return self.off_disabled
        if mode == QtGui.QIcon.Active:
            return self.off_active
        if mode == QtGui.QIcon.Selected:
            return self.off_selected
        return self.off_normal

    def _generate_identifier(self):
        prev_value = None
        values = []
        for value in (
            self.on_normal,
            self.off_normal,
            self.on_active,
            self.off_active,
            self.on_selected,
            self.off_selected,
            self.on_disabled,
            self.off_disabled,
        ):
            id_value = ""
            if value != prev_value:
                id_value = self._get_value_id(value)
            values.append(id_value)
            prev_value = value

        return "|".join(values)

    def _get_value_id(self, value):
        if isinstance(value, QtGui.QColor):
            return value.name()
        return str(value)


def _prepare_mapping(option_name):
    mapping = []
    for store_key, alternative_keys in (
        ("on_normal", ["normal", "on", ""]),
        ("off_normal", ["off"]),
        ("on_active", ["active"]),
        ("off_active", []),
        ("on_selected", ["selected"]),
        ("off_selected", []),
        ("on_disabled", ["disabled"]),
        ("off_disabled", []),
    ):
        mapping_keys = [f"{option_name}_{store_key}"]
        for alt_key in alternative_keys:
            key = option_name
            if alt_key:
                key = f"{option_name}_{alt_key}"
            mapping_keys.append(key)
        mapping.append((store_key, mapping_keys))
    return mapping


class IconOptions:
    mapping_color_keys = _prepare_mapping("color")
    mapping_name_keys = _prepare_mapping("icon_name")
    data_keys = {
        "opacity",
        "offset",
        "scale_factor",
        "hflip",
        "vflip",
        "rotate",
    }

    def __init__(
        self,
        char_option: IconSubOption,
        color_option: IconSubOption,
        opacity: Optional[float] = None,
        scale_factor: Optional[float] = None,
        offset: Optional[Position] = None,
        hflip: Optional[bool] = False,
        vflip: Optional[bool] = False,
        rotate: Optional[int] = 0,
    ):
        if opacity is None:
            opacity = 1.0
        if scale_factor is None:
            scale_factor = 1.0

        self._identifier = None
        self.char_option = char_option
        self.color_option = color_option
        self.opacity = opacity
        self.scale_factor = scale_factor
        self.offset = offset
        self.hflip = hflip
        self.vflip = vflip
        self.rotate = rotate

    @property
    def identifier(self):
        if self._identifier is None:
            self._identifier = self._generate_identifier()
        return self._identifier

    def get_color_for_state(self, state, mode) -> QtGui.QColor:
        return self.color_option.get_value_for_state(state, mode)

    def get_char_for_state(self, state, mode) -> str:
        return self.char_option.get_value_for_state(state, mode)

    @classmethod
    def from_data(cls, **kwargs):
        new_kwargs = {
            key: value
            for key, value in kwargs.items()
            if key in cls.data_keys and value is not None
        }
        color_kwargs = cls._prepare_mapping_values(
            cls.mapping_color_keys, kwargs
        )
        name_kwargs = cls._prepare_mapping_values(
            cls.mapping_name_keys, kwargs
        )
        char_kwargs = {
            key: get_icon_name_char(value)
            for key, value in name_kwargs.items()
        }

        new_kwargs["color_option"] = IconSubOption(**color_kwargs)
        new_kwargs["char_option"] = IconSubOption(**char_kwargs)
        return cls(**new_kwargs)

    @classmethod
    def _prepare_mapping_values(cls, mapping, kwargs):
        mapping_values = {}
        for store_key, mapping_keys in mapping:
            for key in mapping_keys:
                value = kwargs.pop(key, None)
                if value is not None:
                    mapping_values[store_key] = value
                    break
        return mapping_values

    def _generate_identifier(self):
        return (
            str(value)
            for value in (
                self.char_option.identifier,
                self.color_option.identifier,
                self.opacity,
                self.scale_factor,
                self.offset,
                self.hflip,
                self.vflip,
                self.rotate,
            )
        )
