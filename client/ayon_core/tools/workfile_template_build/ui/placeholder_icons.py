"""Icons of placeholders and of the actions used with them."""

from __future__ import annotations

from typing import Any, Optional

from qtpy import QtGui

from ayon_core.style import get_default_tools_icon_color
from ayon_core.tools.utils import get_qt_icon

DEFAULT_PLACEHOLDER_ICON = {
    "type": "material-symbols",
    "name": "extension",
    "color": get_default_tools_icon_color(),
}

CREATE_ICON = "add"
DELETE_ICON = "delete"
RUN_ICON = "play_arrow"
SELECT_ICON = "my_location"
REFRESH_ICON = "refresh"


def get_placeholder_icon(
    icon_def: Optional[dict[str, Any]]
) -> Optional[QtGui.QIcon]:
    """Icon of a placeholder plugin.

    Args:
        icon_def (Optional[dict[str, Any]]): Icon definition of the plugin.

    Returns:
        Optional[QtGui.QIcon]: Icon of the plugin, or the default placeholder
            icon when the plugin does not define a valid one.

    """
    icon = None
    if icon_def:
        icon = get_qt_icon(icon_def, default=None)
    if icon is None:
        icon = get_qt_icon(DEFAULT_PLACEHOLDER_ICON, default=None)
    return icon


def get_action_icon(icon_name: str) -> Optional[QtGui.QIcon]:
    """Material symbols icon used in menus.

    Args:
        icon_name (str): Name of material symbols icon.

    Returns:
        Optional[QtGui.QIcon]: Icon, None when the name is not available.

    """
    return get_qt_icon(
        {
            "type": "material-symbols",
            "name": icon_name,
            "color": get_default_tools_icon_color(),
        },
        default=None,
    )
