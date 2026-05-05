import logging
import sys
import uuid
from typing import Optional, Any, Callable

from qtpy import QtWidgets, QtGui, QtCore
import qtawesome

from ayon_core.lib.attribute_definitions import AbstractAttrDef
from ayon_core.tools.utils import DeselectableTreeView
from ayon_core.tools.loader.drag_drop import (
    encode_loader_drag_payload,
    loader_payload_to_bytes,
    decode_loader_drag_payload_from_mime,
    LOADER_PAYLOAD_MIME_TYPE,
)
from ayon_core.tools.attribute_defs import AttributeDefinitionsDialog
from ayon_core.tools.utils.widgets import (
    OptionalMenu,
    OptionalAction,
    OptionDialog,
)
from ayon_core.tools.utils import get_qt_icon
from ayon_core.tools.loader.abstract import ActionItem

_log = logging.getLogger(__name__)


def _format_payload_summary(project_name, entity_type, entity_ids, action_items):
    """Build a one-line payload summary for debug logs."""
    entity_list = list(entity_ids) if entity_ids else []
    id_previews = [str(eid)[:8] + ("..." if len(str(eid)) > 8 else "") for eid in entity_list[:2]]
    action_ids = [getattr(a, "identifier", str(a)) for a in (action_items or [])]
    return (
        f"project_name={project_name} entity_type={entity_type} entity_ids={len(entity_list)} "
        f"ids={id_previews} actions={len(action_items or [])} {action_ids}"
    )


def _format_payload_summary_from_dict(payload):
    """Build a one-line payload summary from decoded payload dict."""
    if not payload or not isinstance(payload, dict):
        return "payload=invalid"
    entity_ids = payload.get("entity_ids") or []
    actions = payload.get("actions") or []
    id_previews = [str(eid)[:8] + ("..." if len(str(eid)) > 8 else "") for eid in entity_ids[:2]]
    action_ids = [a.get("identifier", "") for a in actions]
    return (
        f"project_name={payload.get('project_name', '')} entity_type={payload.get('entity_type', '')} "
        f"entity_ids={len(entity_ids)} ids={id_previews} actions={len(actions)} {action_ids}"
    )


def _set_file_urls_on_mime_data(mime_data: QtCore.QMimeData, paths: list) -> None:
    """Set file URLs on mime data for cross-platform drag (text/uri-list).
    On Windows, sets Preferred DropEffect to 5 (copy) so Explorer copies instead of moves.
    """
    if not paths:
        return
    urls = [QtCore.QUrl.fromLocalFile(p) for p in paths]
    mime_data.setUrls(urls)
    if sys.platform == "win32":
        mime_data.setData(
            "Preferred DropEffect",
            QtCore.QByteArray((5).to_bytes(4, "little")),
        )


def _make_drag_pixmap(label):
    """Build a visible drag pixmap with non-transparent background (Windows-friendly)."""
    pixmap = QtGui.QPixmap(160, 32)
    pixmap.fill(QtGui.QColor(50, 50, 50, 255))
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.setRenderHint(QtGui.QPainter.TextAntialiasing)
    rect = pixmap.rect().adjusted(2, 2, -3, -3)
    painter.setBrush(QtGui.QColor(60, 60, 60, 240))
    painter.setPen(QtGui.QColor(100, 100, 100))
    painter.drawRoundedRect(rect, 4, 4)
    painter.setPen(QtCore.Qt.white)
    painter.drawText(rect, QtCore.Qt.AlignCenter, label)
    painter.end()
    return pixmap


class LoaderDragTreeView(DeselectableTreeView):
    """Tree view that supports dragging loader action payload."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragOnly)
        self._drag_data_callback = None
        self._drag_start_pos = None
        self._last_drag_summary = None

    def set_drag_data_callback(self, callback: Optional[Callable[[], Optional[tuple]]]):
        self._drag_data_callback = callback

    def mousePressEvent(self, event):
        """Bypass DeselectableTreeView so Ctrl is never injected; drag can start."""
        index = self.indexAt(event.pos())
        if not index.isValid():
            self.clearSelection()
            self.setCurrentIndex(QtCore.QModelIndex())
            self._drag_start_pos = None
        else:
            model = self.model()
            if model and (model.flags(index) & QtCore.Qt.ItemIsDragEnabled):
                self._drag_start_pos = event.pos()
            else:
                self._drag_start_pos = None
        QtWidgets.QTreeView.mousePressEvent(self, event)

    def mouseMoveEvent(self, event):
        """Fallback: start drag on move when Qt's internal path never calls startDrag."""
        if (
            self._drag_start_pos is not None
            and event.buttons() & QtCore.Qt.LeftButton
            and self._drag_data_callback
        ):
            dist = (event.pos() - self._drag_start_pos).manhattanLength()
            if dist >= QtWidgets.QApplication.startDragDistance():
                self._drag_start_pos = None
                mime_data, entity_ids = self._build_drag_mime_data()
                if mime_data is not None:
                    if _log and getattr(self, "_last_drag_summary", None):
                        _log.debug(
                            "mouseMoveEvent: starting fallback drag %s",
                            self._last_drag_summary,
                        )
                    count = len(entity_ids)
                    label = "Load" if count <= 1 else f"Load ({count} items)"
                    drag = QtGui.QDrag(self)
                    drag.setMimeData(mime_data)
                    drag.setPixmap(_make_drag_pixmap(label))
                    drag.setHotSpot(QtCore.QPoint(24, 16))
                    result = drag.exec_(QtCore.Qt.CopyAction)
                    if _log:
                        _log.debug(
                            "mouseMoveEvent: drag finished result=%s",
                            result,
                        )
                    return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    def _build_drag_mime_data(self):
        """Build (QMimeData, entity_ids) from callback; (None, ()) if not draggable."""
        self._last_drag_summary = None
        if not self._drag_data_callback:
            if _log:
                _log.debug("_build_drag_mime_data: reason=no_callback")
            return None, ()
        try:
            result = self._drag_data_callback()
        except Exception as e:
            if _log:
                _log.debug(
                    "_build_drag_mime_data: callback raised %s",
                    e,
                    exc_info=True,
                )
            return None, ()
        if not result:
            if _log:
                _log.debug("_build_drag_mime_data: reason=callback_returned_none")
            return None, ()
        try:
            project_name, entity_ids, entity_type = result
        except (ValueError, TypeError) as e:
            if _log:
                _log.debug(
                    "_build_drag_mime_data: unpack result failed %s",
                    e,
                )
            return None, ()
        if not entity_ids:
            if _log:
                _log.debug(
                    "_build_drag_mime_data: reason=no_entity_ids (product row only? select version row)"
                )
            return None, ()
        controller = getattr(self.parent(), "_controller", None)
        action_items = []
        if controller and hasattr(controller, "get_drag_drop_action_items"):
            try:
                action_items = controller.get_drag_drop_action_items(
                    project_name, set(entity_ids), entity_type
                ) or []
            except Exception as e:
                if _log:
                    _log.debug(
                        "_build_drag_mime_data: get_drag_drop_action_items raised %s",
                        e,
                    )
        try:
            payload = encode_loader_drag_payload(
                project_name, entity_type, list(entity_ids), action_items
            )
            mime_data = QtCore.QMimeData()
            mime_data.setData(
                LOADER_PAYLOAD_MIME_TYPE,
                QtCore.QByteArray(loader_payload_to_bytes(payload)),
            )
            controller = getattr(self.parent(), "_controller", None)
            if controller and hasattr(controller, "get_drag_drop_file_paths"):
                try:
                    paths = controller.get_drag_drop_file_paths(
                        project_name, set(entity_ids), entity_type
                    )
                    _set_file_urls_on_mime_data(mime_data, paths)
                except Exception as e:
                    if _log:
                        _log.debug(
                            "_build_drag_mime_data: get_drag_drop_file_paths %s",
                            e,
                            exc_info=True,
                        )
            summary = _format_payload_summary(
                project_name, entity_type, entity_ids, action_items
            )
        except Exception as e:
            if _log:
                _log.debug(
                    "_build_drag_mime_data: encode/summary failed %s",
                    e,
                    exc_info=True,
                )
            return None, ()
        if _log:
            _log.debug("_build_drag_mime_data: %s", summary)
        self._last_drag_summary = summary
        return mime_data, entity_ids

    def startDrag(self, supportedActions):
        if _log:
            _log.debug(
                "startDrag: entry supportedActions=%s",
                supportedActions,
            )
        try:
            mime_data, entity_ids = self._build_drag_mime_data()
        except Exception as e:
            if _log:
                _log.debug(
                    "startDrag: _build_drag_mime_data raised %s",
                    e,
                    exc_info=True,
                )
            mime_data, entity_ids = None, ()
        if _log:
            _log.debug(
                "startDrag: mime_data built=%s, fallback to super=%s",
                mime_data is not None,
                mime_data is None,
            )
        if mime_data is not None:
            if _log and getattr(self, "_last_drag_summary", None):
                _log.debug(
                    "startDrag: executing drag with custom mime_data %s",
                    self._last_drag_summary,
                )
            count = len(entity_ids)
            label = "Load" if count <= 1 else f"Load ({count} items)"
            drag = QtGui.QDrag(self)
            drag.setMimeData(mime_data)
            drag.setPixmap(_make_drag_pixmap(label))
            drag.setHotSpot(QtCore.QPoint(24, 16))
            result = drag.exec_(QtCore.Qt.CopyAction)
            if _log:
                _log.debug(
                    "startDrag: drag finished result=%s",
                    result,
                )
            return
        model = self.model()
        sel = self.selectionModel()
        if model and sel:
            indexes = sel.selectedIndexes()
            model_mime = model.mimeData(indexes) if indexes else None
            if model_mime is not None and model_mime.hasFormat(LOADER_PAYLOAD_MIME_TYPE):
                payload = decode_loader_drag_payload_from_mime(model_mime)
                if payload:
                    if _log:
                        _log.debug(
                            "startDrag: using model mimeData + custom pixmap %s",
                            _format_payload_summary_from_dict(payload),
                        )
                    entity_ids = payload.get("entity_ids") or []
                    project_name = payload.get("project_name") or ""
                    entity_type = payload.get("entity_type") or "version"
                    controller = getattr(self.parent(), "_controller", None)
                    if controller and hasattr(controller, "get_drag_drop_file_paths") and entity_ids:
                        try:
                            paths = controller.get_drag_drop_file_paths(
                                project_name, set(entity_ids), entity_type
                            )
                            _set_file_urls_on_mime_data(model_mime, paths)
                        except Exception:
                            pass
                    count = len(entity_ids)
                    label = "Load" if count <= 1 else f"Load ({count} items)"
                    drag = QtGui.QDrag(self)
                    drag.setMimeData(model_mime)
                    drag.setPixmap(_make_drag_pixmap(label))
                    drag.setHotSpot(QtCore.QPoint(24, 16))
                    result = drag.exec_(QtCore.Qt.CopyAction)
                    if _log:
                        _log.debug(
                            "startDrag: drag finished result=%s",
                            result,
                        )
                    return
        if _log:
            _log.debug(
                "startDrag: no payload (product row only?); fallback to super"
            )
        super().startDrag(supportedActions)


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

    action_items = [
        item for item in action_items
        if getattr(item, "show_in_context_menu", True)
    ]

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


def show_loader_drop_action_picker(
    actions: list[dict[str, Any]],
    callback: Callable[[str, Optional[dict], dict, dict], None],
    parent: Optional[QtWidgets.QWidget] = None,
) -> bool:
    """Show a small modal to pick one loader action when multiple are available.

    Args:
        actions: List of dicts with "identifier", "data", "label" (and optionally
            "default_for_drag_drop"). Used when more than one drag-drop action
            is valid and none is the single default.
        callback: Callable(identifier, data, options, form_values) to run the
            chosen action. options and form_values can be empty dicts.
        parent: Parent widget for the dialog.

    Returns:
        True if user picked an action and callback was called, False if cancelled.
    """
    if not actions:
        return False
    if len(actions) == 1:
        a = actions[0]
        callback(
            a.get("identifier", ""),
            a.get("data"),
            {},
            {},
        )
        return True

    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle("Choose load action")
    layout = QtWidgets.QVBoxLayout(dialog)
    list_widget = QtWidgets.QListWidget()
    for a in actions:
        list_widget.addItem(a.get("label", a.get("identifier", "Unknown")))
    list_widget.setCurrentRow(0)
    layout.addWidget(list_widget)
    buttons = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
    )
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    def on_accept():
        row = list_widget.currentRow()
        if 0 <= row < len(actions):
            a = actions[row]
            callback(
                a.get("identifier", ""),
                a.get("data"),
                {},
                {},
            )

    buttons.accepted.connect(on_accept)

    if dialog.exec_() == QtWidgets.QDialog.Accepted:
        return True
    return False
