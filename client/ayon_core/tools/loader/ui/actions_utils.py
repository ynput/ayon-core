import uuid
import re
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
    """Sort actions by order and then by their visible group/name."""

    action_item, group_label, label = item
    if group_label is None:
        group_label = label
        label = ""
    return action_item.order, group_label, label


def _split_representation_label(label: str):
    match = re.match(r"^(.+?)\s\(([^()]+)\)$", label)
    if not match:
        return None
    return match.group(1), match.group(2)


def _exec_menu_at(menu, global_point):
    exec_fn = getattr(menu, "exec", None)
    if exec_fn is None:
        exec_fn = menu.exec_
    return exec_fn(global_point)


def _action_payload_id(action):
    item_id = action.data()
    if hasattr(item_id, "toPyObject"):
        item_id = item_id.toPyObject()
    return item_id


def _action_targets_representations(action_item):
    if getattr(action_item, "representation_ids", None):
        return True

    data = action_item.data or {}
    if data.get("entity_type") == "representation":
        return True
    return (
        data.get("representation_id") is not None
        or data.get("representation_ids") is not None
    )


def show_actions_menu(
    action_items: list[ActionItem],
    global_point: QtCore.QPoint,
    one_item_selected: bool,
    parent: QtWidgets.QWidget,
    use_representation_submenus: bool = True,
) -> tuple[Optional[ActionItem], Optional[dict[str, Any]]]:
    selected_action_item = None
    selected_options = None

    if not action_items:
        menu = QtWidgets.QMenu(parent)
        action = _get_no_loader_action(menu, one_item_selected)
        menu.addAction(action)
        _exec_menu_at(menu, global_point)
        return selected_action_item, selected_options

    menu = OptionalMenu(parent)

    representation_groups = {}
    flat_items = []
    for action_item in action_items:
        if (
            action_item.group_label is None
            and getattr(action_item, "representation_ids", None)
        ):
            split_label = _split_representation_label(action_item.label)
            if split_label:
                base_label, repre_label = split_label
                representation_groups.setdefault(base_label, []).append(
                    (repre_label, action_item)
                )
                continue
        flat_items.append(action_item)

    action_items_by_id = {}

    def _add_qaction_for_item(qmenu, item_label, action_item):
        item_id = uuid.uuid4().hex
        action_items_by_id[item_id] = action_item
        item_options = action_item.options
        icon = get_qt_icon(action_item.icon)
        use_option = bool(item_options)
        action = OptionalAction(
            item_label,
            icon,
            use_option,
            qmenu
        )
        if use_option:
            action.set_option_tip(item_options)
        tip = action_item.tooltip
        if tip:
            action.setToolTip(tip)
            action.setStatusTip(tip)
        action.setData(item_id)
        qmenu.addAction(action)
        return icon

    action_groups = {}
    root_entries = []
    for action_item in flat_items:
        group_label = action_item.group_label
        if group_label:
            action_groups.setdefault(group_label, []).append(action_item)
        else:
            root_entries.append((
                "action",
                action_item.order,
                action_item.label,
                (action_item, action_item.label),
            ))

    for group_label, items in action_groups.items():
        first_item = min(items, key=lambda item: (item.order, item.label))
        if (
            not use_representation_submenus
            and len(items) == 1
            and _action_targets_representations(first_item)
        ):
            root_entries.append((
                "action",
                first_item.order,
                group_label,
                (first_item, group_label),
            ))
            continue

        root_entries.append((
            "group",
            first_item.order,
            group_label,
            (group_label, items),
        ))

    for base_label, items in representation_groups.items():
        if len(items) == 1:
            _, action_item = items[0]
            item_label = action_item.label
            if not use_representation_submenus:
                item_label = base_label
            root_entries.append((
                "action",
                action_item.order,
                item_label,
                (action_item, item_label),
            ))
            continue
        first_item = min(items, key=lambda item: (item[1].order, item[0]))
        root_entries.append((
            "representation_group",
            first_item[1].order,
            base_label,
            (base_label, items),
        ))

    for entry_type, _, _, payload in sorted(
        root_entries, key=lambda item: (item[1], item[2])
    ):
        if entry_type == "action":
            action_item, item_label = payload
            _add_qaction_for_item(menu, item_label, action_item)
            continue

        if entry_type == "group":
            group_label, items = payload
            group_menu = OptionalMenu(group_label, menu)
            group_icon_set = False
            for action_item in sorted(
                items,
                key=lambda item: _actions_sorter(
                    (item, item.group_label, item.label)
                )
            ):
                icon = _add_qaction_for_item(
                    group_menu, action_item.label, action_item
                )
                if icon is not None and not group_icon_set:
                    group_menu.setIcon(icon)
                    group_icon_set = True
            menu.addMenu(group_menu)
            continue

        base_label, items = payload
        sub_menu = OptionalMenu(base_label, menu)
        sub_icon_set = False
        for repre_label, action_item in sorted(
            items, key=lambda item: (item[1].order, item[0].lower())
        ):
            icon = _add_qaction_for_item(
                sub_menu, repre_label, action_item
            )
            if icon is not None and not sub_icon_set:
                sub_menu.setIcon(icon)
                sub_icon_set = True
        menu.addMenu(sub_menu)

    action = _exec_menu_at(menu, global_point)
    if action is not None:
        item_id = _action_payload_id(action)
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
