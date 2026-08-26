"""Group-by options, enums, and attribute-icon helpers for the review widget.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


def get_attribute_icon(
    name: str,
    attr_type: str | None,
    has_enum: bool,
) -> str:
    """Return a Material-icon name for a version attribute.

    Based on ``shared/src/util/getAttributeIcon.ts``.

    Args:
        name: Attribute name.
        attr_type: Attribute type string (e.g. ``"integer"``).
        has_enum: Whether the attribute defines an ``enum`` list.

    Returns:
        Material Symbols icon name string.
    """
    custom_icons: dict[str, str] = {
        "status": "arrow_circle_right",
        "assignees": "person",
        "author": "person",
        "tags": "local_offer",
        "priority": "keyboard_double_arrow_up",
        "fps": "30fps_select",
        "resolutionWidth": "settings_overscan",
        "resolutionHeight": "settings_overscan",
        "pixelAspect": "stop",
        "clipIn": "line_start_diamond",
        "clipOut": "line_end_diamond",
        "frameStart": "line_start_circle",
        "frameEnd": "line_end_circle",
        "handleStart": "line_start_square",
        "handleEnd": "line_end_square",
        "fullName": "id_card",
        "email": "alternate_email",
        "developerMode": "code",
        "productGroup": "inventory_2",
        "machine": "computer",
        "comment": "comment",
        "colorSpace": "palette",
        "description": "description",
    }

    type_icons: dict[str, str] = {
        "integer": "pin",
        "float": "speed_1_2",
        "boolean": "radio_button_checked",
        "datetime": "calendar_month",
        "list_of_strings": "format_list_bulleted",
        "list_of_integers": "format_list_numbered",
        "list_of_any": "format_list_bulleted",
        "list_of_submodels": "format_list_bulleted",
        "dict": "format_list_bulleted",
        "string": "title",
    }

    if name in custom_icons:
        return custom_icons[name]
    if has_enum:
        return "format_list_bulleted"
    if attr_type and attr_type in type_icons:
        return type_icons[attr_type]
    return "format_list_bulleted"


class GroupBySource(Enum):
    """Discriminant for whether a group-by option is built-in or attribute."""

    BUILTIN = "builtin"
    ATTRIBUTE = "attribute"


@dataclass(frozen=True)
class GroupByOption:
    """A single group-by axis available in the version table."""

    key: str
    label: str
    icon: str = "label"
    source: GroupBySource = GroupBySource.BUILTIN
    attribute_name: str | None = None


# Keys for the built-in group-by options.
GROUP_BY_NONE_KEY = "none"
GROUP_BY_PRODUCT_KEY = "product"
GROUP_BY_STATUS_KEY = "status"
GROUP_BY_TAGS_KEY = "tags"
GROUP_BY_TASK_TYPE_KEY = "task_type"
GROUP_BY_PRODUCT_TYPE_KEY = "product_type"

BUILTIN_GROUPS: list[GroupByOption] = [
    GroupByOption(GROUP_BY_NONE_KEY, "None", "close"),
    GroupByOption(GROUP_BY_PRODUCT_KEY, "Product", "inventory_2"),
    GroupByOption(GROUP_BY_STATUS_KEY, "Status", "arrow_circle_right"),
    GroupByOption(GROUP_BY_TAGS_KEY, "Tags", "local_offer"),
    GroupByOption(GROUP_BY_TASK_TYPE_KEY, "Task type", "check_circle"),
    GroupByOption(GROUP_BY_PRODUCT_TYPE_KEY, "Product type", "category"),
]


def build_attribute_groups(
    version_attributes: dict[str, dict[str, Any]],
) -> list[GroupByOption]:
    """Build attribute-based group-by options from project version attributes.

    Args:
        version_attributes: Dict mapping attribute name to its definition
            dict (as returned by ``ayon_api.get_attributes_for_type``).

    Returns:
        List of :class:`GroupByOption` instances, one per attribute.
    """
    return [
        GroupByOption(
            key=f"attr:{attr_name}",
            label=attr_def.get("title") or attr_name,
            icon=get_attribute_icon(
                attr_name,
                attr_def.get("type"),
                attr_def.get("enum") is not None,
            ),
            source=GroupBySource.ATTRIBUTE,
            attribute_name=attr_name,
        )
        for attr_name, attr_def in version_attributes.items()
    ]
