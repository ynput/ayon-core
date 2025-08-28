import uuid
import re

from qtpy import QtWidgets, QtGui
import qtawesome

from ayon_core.lib.attribute_definitions import AbstractAttrDef
from ayon_core.tools.attribute_defs import AttributeDefinitionsDialog
from ayon_core.tools.utils.widgets import (
    OptionalMenu,
    OptionalAction,
    OptionDialog,
)
from ayon_core.tools.utils import get_qt_icon


def show_actions_menu(action_items, global_point, one_item_selected, parent):
    selected_action_item = None
    selected_options = None

    if not action_items:
        menu = QtWidgets.QMenu(parent)
        action = _get_no_loader_action(menu, one_item_selected)
        menu.addAction(action)
        menu.exec_(global_point)
        return selected_action_item, selected_options

    menu = OptionalMenu(parent)

    # Group representation-based actions by their loader label so we can
    # display a submenu with the representations instead of duplicating the
    # loader entry for each representation.
    # We rely on the current label convention "<Loader Label> (<repre>)" to
    # extract the representation name from the label. Non-representation
    # actions stay flat in the root menu.
    label_re = re.compile(r"^(.+?)\s\(([^()]+)\)$")

    grouped: dict[str, list[tuple[str, object]]] = {}
    flat_items = []
    for ai in action_items:
        # Consider it representation-based when it has representation ids and
        # the label contains a trailing " (name)".
        if getattr(ai, "representation_ids", None):
            m = label_re.match(ai.label)
            if m:
                base_label = m.group(1)
                repre_label = m.group(2)
                grouped.setdefault(base_label, []).append((repre_label, ai))
                continue
        flat_items.append(ai)

    action_items_by_id = {}

    def _add_qaction_for_item(qmenu, item_label, ai):
        item_id = uuid.uuid4().hex
        action_items_by_id[item_id] = ai
        item_options = ai.options
        icon = get_qt_icon(ai.icon)
        use_option = bool(item_options)
        action = OptionalAction(
            item_label,
            icon,
            use_option,
            qmenu
        )
        if use_option:
            action.set_option_tip(item_options)
        tip = ai.tooltip
        if tip:
            action.setToolTip(tip)
            action.setStatusTip(tip)
        action.setData(item_id)
        qmenu.addAction(action)

    # Add flat actions first
    for ai in flat_items:
        _add_qaction_for_item(menu, ai.label, ai)

    # Add grouped actions. If only a single representation exists for a
    # loader, keep it flat for compactness; otherwise create submenu.
    for base_label, items in grouped.items():
        if len(items) == 1:
            # Single representation - show as a single flat action with the
            # existing label to avoid unnecessary submenu nesting.
            repre_label, ai = items[0]
            _add_qaction_for_item(menu, f"{base_label} ({repre_label})", ai)
            continue

        sub = OptionalMenu(menu)
        sub.setTitle(base_label)
        # Use the icon from the first item for the submenu title
        sub_icon = get_qt_icon(items[0][1].icon)
        if sub_icon is not None:
            sub.setIcon(sub_icon)
        for repre_label, ai in sorted(items, key=lambda t: t[0].lower()):
            _add_qaction_for_item(sub, repre_label, ai)
        menu.addMenu(sub)

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
