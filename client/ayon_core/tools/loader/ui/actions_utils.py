import uuid
from typing import Optional, Any

from qtpy import QtWidgets, QtGui, QtCore
import qtawesome

from ayon_core.lib.attribute_definitions import AbstractAttrDef
from ayon_core.tools.attribute_defs import AttributeDefinitionsDialog
from ayon_core.tools.utils.widgets import (
    OptionalMenu,
    OptionalAction,
    OptionDialog,
)
from ayon_core.tools.utils import get_qt_icon
from ayon_core.tools.loader.abstract import ActionItem


def _actions_sorter(item: tuple[ActionItem, str, str]):
    """Sort the Loaders by their order and then their name.

    Returns:
        tuple[int, str]: Sort keys.

    """
    action_item, group_label, label = item
    if group_label is None:
        group_label = label
        label = ""
    return action_item.order, group_label, label


def show_actions_menu(
    action_items: list[ActionItem],
    global_point: QtCore.QPoint,
    one_item_selected: bool,
    parent: QtWidgets.QWidget,
) -> tuple[Optional[ActionItem], Optional[dict[str, Any]]]:
    selected_action_item = None
    selected_options = None

    if not action_items:
        menu = QtWidgets.QMenu(parent)
        action = _get_no_loader_action(menu, one_item_selected)
        menu.addAction(action)
        menu.exec_(global_point)
        return selected_action_item, selected_options

    menu = OptionalMenu(parent)

    action_items_with_labels = []
    for action_item in action_items:
        action_items_with_labels.append(
            (action_item, action_item.group_label, action_item.label)
        )

    group_menu_by_label = {}
    action_items_by_id = {}
    for item in sorted(action_items_with_labels, key=_actions_sorter):
        action_item, _, _ = item
        item_id = uuid.uuid4().hex
        action_items_by_id[item_id] = action_item
        item_options = action_item.options
        icon = get_qt_icon(action_item.icon)
        use_option = bool(item_options)
        action = OptionalAction(
            action_item.label,
            icon,
            use_option,
            menu
        )
        if use_option:
            # Add option box tip
            action.set_option_tip(item_options)

        tip = action_item.tooltip
        if tip:
            action.setToolTip(tip)
            action.setStatusTip(tip)

        action.setData(item_id)

        group_label = action_item.group_label
        if group_label:
            group_menu = group_menu_by_label.get(group_label)
            if group_menu is None:
                group_menu = OptionalMenu(group_label, menu)
                if icon is not None:
                    group_menu.setIcon(icon)
                menu.addMenu(group_menu)
                group_menu_by_label[group_label] = group_menu
            group_menu.addAction(action)
        else:
            menu.addAction(action)

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


def _get_no_loader_action(menu, one_item_selected):
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
