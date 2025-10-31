import os
import itertools
import uuid
from typing import List

from qtpy import QtWidgets, QtGui, QtCore
import qtawesome

from ayon_core.lib.attribute_definitions import AbstractAttrDef
from ayon_core.tools.attribute_defs import AttributeDefinitionsDialog
from ayon_core.tools.utils.widgets import (
    OptionalMenu,
    OptionalAction,
    OptionDialog,
)
from ayon_core.tools.loader.models.actions import ActionItem
from ayon_core.tools.utils import get_qt_icon


def show_actions_menu(
        action_items: List[ActionItem],
        global_point: QtCore.QPoint,
        one_item_selected: bool,
        parent: QtCore.QObject):
    selected_action_item = None
    selected_options = None

    # Can be any of `never`, `multiples`, `always`
    grouping_mode = os.getenv("AYON_LOADER_GROUP_MODE", "always")

    if not action_items:
        menu = QtWidgets.QMenu(parent)
        action = _get_no_loader_action(menu, one_item_selected)
        menu.addAction(action)
        menu.exec_(global_point)
        return selected_action_item, selected_options

    menu = OptionalMenu(parent)

    action_items_by_id = {}
    for key, group in itertools.groupby(
            action_items, key=lambda x: x.identifier):
        group_action_items: List[ActionItem] = list(group)

        target_menu = menu

        is_grouped = True
        if grouping_mode == "never":
            # Never group
            is_grouped = False
        if grouping_mode == "multiples":
            # Only group if more than one action item from a loader
            is_grouped = len(group_action_items) > 1
        elif grouping_mode == "always":
            # Always
            is_grouped = True

        if is_grouped:
            # Attach to a submenu
            label = group_action_items[0].label.rsplit(" (", 1)[0]
            icon = get_qt_icon(group_action_items[0].icon)
            target_menu = menu.addMenu(icon, label)

        for action_item in group_action_items:
            item_id = uuid.uuid4().hex
            action_items_by_id[item_id] = action_item
            item_options = action_item.options
            icon = get_qt_icon(action_item.icon)
            use_option = bool(item_options)
            label = action_item.label
            if is_grouped:
                label = label.rsplit(" (", 1)[-1].rstrip(") ")
            action = OptionalAction(
                label,
                icon,
                use_option,
                target_menu
            )
            if use_option:
                # Add option box tip
                action.set_option_tip(item_options)

            tip = action_item.tooltip
            if tip:
                action.setToolTip(tip)
                action.setStatusTip(tip)

            action.setData(item_id)

            target_menu.addAction(action)

    action = menu.exec_(global_point)
    if action is not None:
        item_id = action.data()
        selected_action_item = action_items_by_id.get(item_id)

    if selected_action_item is not None:
        selected_options = _get_options(action, selected_action_item, parent)

    return selected_action_item, selected_options


def _get_options(action, action_item, parent):
    """Provides dialog to select value from loader provided options.

    Loader can provide static or dynamically created options based on
    AttributeDefinitions, and for backwards compatibility qargparse.

    Args:
        action (OptionalAction) - Action object in menu.
        action_item (ActionItem) - Action item with context information.
        parent (QtCore.QObject) - Parent object for dialog.

    Returns:
        Union[dict[str, Any], None]: Selected value from attributes or
            'None' if dialog was cancelled.
    """

    # Pop option dialog
    options = action_item.options
    if not getattr(action, "optioned", False) or not options:
        return {}

    dialog_title = action.label + " Options"
    if isinstance(options[0], AbstractAttrDef):
        qargparse_options = False
        dialog = AttributeDefinitionsDialog(
            options, title=dialog_title, parent=parent
        )
    else:
        qargparse_options = True
        dialog = OptionDialog(parent)
        dialog.create(options)
        dialog.setWindowTitle(dialog_title)

    if not dialog.exec_():
        return None

    # Get option
    if qargparse_options:
        return dialog.parse()
    return dialog.get_values()


def _get_no_loader_action(menu: QtWidgets.QMenu, one_item_selected: bool):
    """Creates dummy no loader option in 'menu'"""

    if one_item_selected:
        submsg = "this version."
    else:
        submsg = "your selection."
    msg = "No compatible loaders for {}".format(submsg)
    icon = qtawesome.icon(
        "fa.exclamation",
        color=QtGui.QColor(255, 51, 0)
    )
    return QtWidgets.QAction(icon, ("*" + msg), menu)
