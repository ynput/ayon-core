import time
import uuid
import collections

from qtpy import QtWidgets, QtCore, QtGui

from ayon_core.lib import Logger
from ayon_core.lib.attribute_definitions import (
    UILabelDef,
    EnumDef,
    TextDef,
    BoolDef,
    NumberDef,
    HiddenDef,
)
from ayon_core.tools.flickcharm import FlickCharm
from ayon_core.tools.utils import get_qt_icon, SquareButton
from ayon_core.tools.attribute_defs import AttributeDefinitionsDialog
from ayon_core.tools.launcher.abstract import WebactionContext

from .resources import get_options_image_path

ANIMATION_LEN = 7

ACTION_ID_ROLE = QtCore.Qt.UserRole + 1
ACTION_TYPE_ROLE = QtCore.Qt.UserRole + 2
ACTION_IS_GROUP_ROLE = QtCore.Qt.UserRole + 3
ACTION_SORT_ROLE = QtCore.Qt.UserRole + 4
ACTION_ADDON_NAME_ROLE = QtCore.Qt.UserRole + 5
ACTION_ADDON_VERSION_ROLE = QtCore.Qt.UserRole + 6
ANIMATION_START_ROLE = QtCore.Qt.UserRole + 7
ANIMATION_STATE_ROLE = QtCore.Qt.UserRole + 8


def _variant_label_sort_getter(action_item):
    """Get variant label value for sorting.

    Make sure the output value is a string.

    Args:
        action_item (ActionItem): Action item.

    Returns:
        str: Variant label or empty string.
    """

    return action_item.variant_label or ""


# --- Replacement for QAction for action variants ---
class LauncherSettingsButton(SquareButton):
    _settings_icon = None

    def __init__(self, parent):
        super().__init__(parent)
        self.setIcon(self._get_settings_icon())

    @classmethod
    def _get_settings_icon(cls):
        if cls._settings_icon is None:
            cls._settings_icon = get_qt_icon({
                "type": "material-symbols",
                "name": "settings",
            })
        return cls._settings_icon


class ActionVariantWidget(QtWidgets.QFrame):
    settings_requested = QtCore.Signal(str)

    def __init__(self, item_id, label, has_settings, parent):
        super().__init__(parent)

        label_widget = QtWidgets.QLabel(label, self)
        settings_btn = None
        if has_settings:
            settings_btn = LauncherSettingsButton(self)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 4, 4)
        layout.setSpacing(0)
        layout.addWidget(label_widget, 1)
        if settings_btn is not None:
            layout.addSpacing(6)
            layout.addWidget(settings_btn, 0)

            settings_btn.clicked.connect(self._on_settings_clicked)

        self._item_id = item_id
        self._label_widget = label_widget
        self._settings_btn = settings_btn

    def showEvent(self, event):
        super().showEvent(event)
        # Make sure to set up current state
        self._set_hover_properties(self.underMouse())

    def enterEvent(self, event):
        """Handle mouse enter event."""
        self._set_hover_properties(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Handle mouse enter event."""
        self._set_hover_properties(False)
        super().leaveEvent(event)

    def _on_settings_clicked(self):
        self.settings_requested.emit(self._item_id)

    def _set_hover_properties(self, hovered):
        state = "hover" if hovered else ""
        if self.property("state") != state:
            self.setProperty("state", state)
            self.style().polish(self)


class ActionVariantAction(QtWidgets.QWidgetAction):
    """Menu action with settings button."""
    settings_requested = QtCore.Signal(str)

    def __init__(self, item_id, label, has_settings, parent):
        super().__init__(parent)
        self._item_id = item_id
        self._label = label
        self._has_settings = has_settings
        self._widget = None

    def createWidget(self, parent):
        widget = ActionVariantWidget(
            self._item_id, self._label, self._has_settings, parent
        )
        widget.settings_requested.connect(self.settings_requested)
        self._widget = widget
        return widget


class ActionsQtModel(QtGui.QStandardItemModel):
    """Qt model for actions.

    Args:
        controller (AbstractLauncherFrontEnd): Controller instance.
    """

    refreshed = QtCore.Signal()

    def __init__(self, controller):
        self._log = Logger.get_logger(self.__class__.__name__)
        super().__init__()

        controller.register_event_callback(
            "selection.project.changed",
            self._on_selection_project_changed,
        )
        controller.register_event_callback(
            "selection.folder.changed",
            self._on_selection_folder_changed,
        )
        controller.register_event_callback(
            "selection.task.changed",
            self._on_selection_task_changed,
        )

        self._controller = controller

        self._items_by_id = {}
        self._action_items_by_id = {}
        self._groups_by_id = {}

        self._selected_project_name = None
        self._selected_folder_id = None
        self._selected_task_id = None

    def get_selected_project_name(self):
        return self._selected_project_name

    def get_selected_folder_id(self):
        return self._selected_folder_id

    def get_selected_task_id(self):
        return self._selected_task_id

    def get_group_items(self, action_id):
        return self._groups_by_id[action_id]

    def get_item_by_id(self, action_id):
        return self._items_by_id.get(action_id)

    def get_action_item_by_id(self, action_id):
        return self._action_items_by_id.get(action_id)

    def _clear_items(self):
        self._items_by_id = {}
        self._action_items_by_id = {}
        self._groups_by_id = {}
        root = self.invisibleRootItem()
        root.removeRows(0, root.rowCount())

    def refresh(self):
        items = self._controller.get_action_items(
            self._selected_project_name,
            self._selected_folder_id,
            self._selected_task_id,
        )
        if not items:
            self._clear_items()
            self.refreshed.emit()
            return

        root_item = self.invisibleRootItem()

        all_action_items_info = []
        action_items_by_id = {}
        items_by_label = collections.defaultdict(list)
        for item in items:
            action_items_by_id[item.identifier] = item
            if not item.variant_label:
                all_action_items_info.append((item, False))
            else:
                items_by_label[item.label].append(item)

        groups_by_id = {}
        for action_items in items_by_label.values():
            action_items.sort(key=_variant_label_sort_getter, reverse=True)
            first_item = next(iter(action_items))
            all_action_items_info.append((first_item, len(action_items) > 1))
            groups_by_id[first_item.identifier] = action_items

        transparent_icon = {"type": "transparent", "size": 256}
        new_items = []
        items_by_id = {}
        for action_item_info in all_action_items_info:
            action_item, is_group = action_item_info
            icon_def = action_item.icon
            if not icon_def:
                icon_def = transparent_icon.copy()

            try:
                icon = get_qt_icon(icon_def)
            except Exception:
                self._log.warning(
                    "Failed to parse icon definition", exc_info=True
                )
                # Use empty icon if failed to parse definition
                icon = get_qt_icon(transparent_icon.copy())

            if is_group:
                label = action_item.label
            else:
                label = action_item.full_label

            item = self._items_by_id.get(action_item.identifier)
            if item is None:
                item = QtGui.QStandardItem()
                item.setData(action_item.identifier, ACTION_ID_ROLE)
                new_items.append(item)

            item.setFlags(QtCore.Qt.ItemIsEnabled)
            item.setData(label, QtCore.Qt.DisplayRole)
            item.setData(icon, QtCore.Qt.DecorationRole)
            item.setData(is_group, ACTION_IS_GROUP_ROLE)
            item.setData(action_item.action_type, ACTION_TYPE_ROLE)
            item.setData(action_item.addon_name, ACTION_ADDON_NAME_ROLE)
            item.setData(action_item.addon_version, ACTION_ADDON_VERSION_ROLE)
            item.setData(action_item.order, ACTION_SORT_ROLE)
            items_by_id[action_item.identifier] = item

        if new_items:
            root_item.appendRows(new_items)

        to_remove = set(self._items_by_id.keys()) - set(items_by_id.keys())
        for identifier in to_remove:
            item = self._items_by_id.pop(identifier)
            self._action_items_by_id.pop(identifier)
            root_item.removeRow(item.row())

        self._groups_by_id = groups_by_id
        self._items_by_id = items_by_id
        self._action_items_by_id = action_items_by_id
        self.refreshed.emit()

    def get_action_config_fields(self, action_id: str):
        action_item = self._action_items_by_id.get(action_id)
        if action_item is not None:
            return action_item.config_fields
        return None

    def _on_selection_project_changed(self, event):
        self._selected_project_name = event["project_name"]
        self._selected_folder_id = None
        self._selected_task_id = None
        self.refresh()

    def _on_selection_folder_changed(self, event):
        self._selected_project_name = event["project_name"]
        self._selected_folder_id = event["folder_id"]
        self._selected_task_id = None
        self.refresh()

    def _on_selection_task_changed(self, event):
        self._selected_project_name = event["project_name"]
        self._selected_folder_id = event["folder_id"]
        self._selected_task_id = event["task_id"]
        self.refresh()


class ActionMenuToolTip(QtWidgets.QFrame):
    def __init__(self, parent):
        super().__init__(parent)

        self.setWindowFlags(QtCore.Qt.ToolTip)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        self.setAutoFillBackground(True)
        self.setBackgroundRole(QtGui.QPalette.Base)

        # Update size on show
        show_timer = QtCore.QTimer()
        show_timer.setSingleShot(True)
        show_timer.setInterval(5)

        # Close widget if is not updated by event
        close_timer = QtCore.QTimer()
        close_timer.setSingleShot(True)
        close_timer.setInterval(100)

        update_state_timer = QtCore.QTimer()
        update_state_timer.setInterval(500)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        close_timer.timeout.connect(self.close)
        show_timer.timeout.connect(self._on_show_timer)
        update_state_timer.timeout.connect(self._on_update_state)

        self._main_layout = main_layout
        self._show_timer = show_timer
        self._close_timer = close_timer
        self._update_state_timer = update_state_timer

        self._showed = False
        self._mouse_entered = False
        self._view_hovered = False
        self._current_id = None
        self._view = None
        self._last_pos = QtCore.QPoint(0, 0)
        self._widgets_by_id = {}

    def showEvent(self, event):
        self._showed = True
        self._update_state_timer.start()
        super().showEvent(event)

    def closeEvent(self, event):
        self._showed = False
        self._update_state_timer.stop()
        self._mouse_entered = False
        super().closeEvent(event)

    def enterEvent(self, event):
        self._mouse_entered = True
        self._close_timer.stop()
        super().leaveEvent(event)

    def leaveEvent(self, event):
        self._mouse_entered = False
        super().leaveEvent(event)
        if not self._view_hovered:
            self._close_timer.start()

    def mouse_entered_view(self):
        self._view_hovered = True

    def mouse_left_view(self):
        self._view_hovered = False
        if not self._mouse_entered:
            self._close_timer.start()

    def show_on_event(self, action_id, action_items, view, event):
        self._close_timer.stop()

        self._view_hovered = True

        is_current = action_id == self._current_id
        if not is_current:
            self._current_id = action_id
            self._view = view
            self._update_items(view, action_items)

        # Nothing to show
        if not self._widgets_by_id:
            if self._showed:
                self.close()
            return

        # Make sure is visible
        update_position = not is_current
        if not self._showed:
            update_position = True
            self.show()

        self._last_pos = QtCore.QPoint(event.globalPos())
        if not update_position:
            # Only resize if is current
            self.resize(self.sizeHint())
        else:
            # Set geometry to position
            # - first make sure widget changes from '_update_items'
            #   are recalculated
            app = QtWidgets.QApplication.instance()
            app.processEvents()
            self._on_update_state()

        self.raise_()
        self._show_timer.start()

    def _on_show_timer(self):
        size = self.sizeHint()
        self.resize(size)

    def _on_update_state(self):
        if not self._view_hovered:
            return
        size = self.sizeHint()
        pos = self._last_pos
        offset = 4
        self.setGeometry(
            pos.x() + offset, pos.y() + offset,
            size.width(), size.height()
        )

    def _update_items(self, view, action_items):
        """Update items in the tooltip."""
        # This method can be used to update the content of the tooltip
        # with new icon, text and settings button visibility.

        remove_ids = set(self._widgets_by_id.keys())
        new_ids = set()
        widgets = []

        any_has_settings = False
        prepared_items = []
        for idx, action_item in enumerate(action_items):
            has_settings = bool(action_item.config_fields)
            if has_settings:
                any_has_settings = True
            prepared_items.append((idx, action_item, has_settings))

        if any_has_settings or len(action_items) > 1:
            for idx, action_item, has_settings in prepared_items:
                widget = self._widgets_by_id.get(action_item.identifier)
                icon = get_qt_icon(action_item.icon)
                label = action_item.full_label
                if widget is None:
                    widget = ActionVariantWidget(
                        action_item.identifier, label, has_settings, self
                    )
                    widget.settings_requested.connect(
                        view.settings_requested
                    )
                    new_ids.add(action_item.identifier)
                    self._widgets_by_id[action_item.identifier] = widget
                else:
                    remove_ids.discard(action_item.identifier)
                widgets.append((idx, widget))

        for action_id in remove_ids:
            widget = self._widgets_by_id.pop(action_id)
            widget.setVisible(False)
            self._main_layout.removeWidget(widget)
            widget.deleteLater()

        for idx, widget in widgets:
            self._main_layout.insertWidget(idx, widget, 0)


class ActionDelegate(QtWidgets.QStyledItemDelegate):
    _cached_extender = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._anim_start_color = QtGui.QColor(178, 255, 246)
        self._anim_end_color = QtGui.QColor(5, 44, 50)
        self._tooltip_widget = None

    def helpEvent(self, event, view, option, index):
        if not index.isValid():
            if self._tooltip_widget is not None:
                self._tooltip_widget.close()
            return False

        action_id = index.data(ACTION_ID_ROLE)
        model = index.model()
        source_model = model.sourceModel()
        if index.data(ACTION_IS_GROUP_ROLE):
            action_items = source_model.get_group_items(action_id)
        else:
            action_items = [source_model.get_action_item_by_id(action_id)]
        if self._tooltip_widget is None:
            self._tooltip_widget = ActionMenuToolTip(view)

        self._tooltip_widget.show_on_event(
            action_id, action_items, view, event
        )
        event.setAccepted(True)
        return True

    def close_tooltip(self):
        if self._tooltip_widget is not None:
            self._tooltip_widget.close()

    def mouse_entered_view(self):
        if self._tooltip_widget is not None:
            self._tooltip_widget.mouse_entered_view()

    def mouse_left_view(self):
        if self._tooltip_widget is not None:
            self._tooltip_widget.mouse_left_view()

    def _draw_animation(self, painter, option, index):
        grid_size = option.widget.gridSize()
        x_offset = int(
            (grid_size.width() / 2)
            - (option.rect.width() / 2)
        )
        item_x = option.rect.x() - x_offset
        rect_offset = grid_size.width() / 20
        size = grid_size.width() - (rect_offset * 2)
        anim_rect = QtCore.QRect(
            item_x + rect_offset,
            option.rect.y() + rect_offset,
            size,
            size
        )

        painter.save()

        painter.setBrush(QtCore.Qt.transparent)

        gradient = QtGui.QConicalGradient()
        gradient.setCenter(QtCore.QPointF(anim_rect.center()))
        gradient.setColorAt(0, self._anim_start_color)
        gradient.setColorAt(1, self._anim_end_color)

        time_diff = time.time() - index.data(ANIMATION_START_ROLE)

        # Repeat 4 times
        part_anim = 2.5
        part_time = time_diff % part_anim
        offset = (part_time / part_anim) * 360
        angle = (offset + 90) % 360

        gradient.setAngle(-angle)

        pen = QtGui.QPen(QtGui.QBrush(gradient), rect_offset)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(
            anim_rect,
            -16 * (angle + 10),
            -16 * offset
        )

        painter.restore()

    @classmethod
    def _get_extender_pixmap(cls, size):
        pix = cls._cached_extender.get(size)
        if pix is not None:
            return pix
        pix = QtGui.QPixmap(get_options_image_path()).scaled(
            size, size,
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation
        )
        cls._cached_extender[size] = pix
        return pix

    def paint(self, painter, option, index):
        painter.setRenderHints(
            QtGui.QPainter.Antialiasing
            | QtGui.QPainter.SmoothPixmapTransform
        )

        if index.data(ANIMATION_STATE_ROLE):
            self._draw_animation(painter, option, index)

        super().paint(painter, option, index)

        if not index.data(ACTION_IS_GROUP_ROLE):
            return

        grid_size = option.widget.gridSize()
        x_offset = int(
            (grid_size.width() / 2)
            - (option.rect.width() / 2)
        )
        item_x = option.rect.x() - x_offset

        tenth_size = int(grid_size.width() / 10)
        extender_size = int(tenth_size * 2.4)

        extender_x = item_x + tenth_size
        extender_y = option.rect.y() + tenth_size

        pix = self._get_extender_pixmap(extender_size)
        painter.drawPixmap(extender_x, extender_y, pix)


class ActionsProxyModel(QtCore.QSortFilterProxyModel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setSortCaseSensitivity(QtCore.Qt.CaseInsensitive)

    def lessThan(self, left, right):
        # Sort by action order and then by label
        left_value = left.data(ACTION_SORT_ROLE)
        right_value = right.data(ACTION_SORT_ROLE)

        # Values are same -> use super sorting
        if left_value == right_value:
            # Default behavior is using DisplayRole
            return super().lessThan(left, right)

        # Validate 'None' values
        if right_value is None:
            return True
        if left_value is None:
            return False
        # Sort values and handle incompatible types
        try:
            return left_value < right_value
        except TypeError:
            return True


class ActionsView(QtWidgets.QListView):
    settings_requested = QtCore.Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.setProperty("mode", "icon")
        self.setObjectName("IconView")
        self.setViewMode(QtWidgets.QListView.IconMode)
        self.setResizeMode(QtWidgets.QListView.Adjust)
        self.setSelectionMode(QtWidgets.QListView.NoSelection)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setWrapping(True)
        self.setGridSize(QtCore.QSize(70, 75))
        self.setIconSize(QtCore.QSize(30, 30))
        self.setSpacing(0)
        self.setWordWrap(True)
        self.setToolTipDuration(150)

        delegate = ActionDelegate(self)
        self.setItemDelegate(delegate)

        # Make view flickable
        flick = FlickCharm(parent=self)
        flick.activateOn(self)

        self._flick = flick
        self._delegate = delegate

    def enterEvent(self, event):
        super().enterEvent(event)
        self._delegate.mouse_entered_view()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._delegate.mouse_left_view()


class ActionsWidget(QtWidgets.QWidget):
    def __init__(self, controller, parent):
        super().__init__(parent)

        self._controller = controller

        view = ActionsView(self)

        model = ActionsQtModel(controller)

        proxy_model = ActionsProxyModel()
        proxy_model.setSourceModel(model)
        view.setModel(proxy_model)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(view)

        animation_timer = QtCore.QTimer()
        animation_timer.setInterval(40)
        animation_timer.timeout.connect(self._on_animation)

        view.clicked.connect(self._on_clicked)
        view.settings_requested.connect(self._show_config_dialog)
        model.refreshed.connect(self._on_model_refresh)

        self._animated_items = set()
        self._animation_timer = animation_timer

        self._view = view
        self._model = model
        self._proxy_model = proxy_model

        self._config_widget = None

        self._set_row_height(1)

    def refresh(self):
        self._model.refresh()

    def handle_webaction_form_event(self, event):
        # NOTE The 'ActionsWidget' should be responsible for handling this
        #   but because we're showing messages to user it is handled by window
        identifier = event["identifier"]
        form = event["form"]
        submit_icon = form["submit_icon"]
        if submit_icon:
            submit_icon = get_qt_icon(submit_icon)

        cancel_icon = form["cancel_icon"]
        if cancel_icon:
            cancel_icon = get_qt_icon(cancel_icon)

        dialog = self._create_attrs_dialog(
            form["fields"],
            form["title"],
            form["submit_label"],
            form["cancel_label"],
            submit_icon,
            cancel_icon,
        )
        dialog.setMinimumSize(380, 180)
        result = dialog.exec_()
        if result != QtWidgets.QDialog.Accepted:
            return
        form_data = dialog.get_values()
        self._controller.trigger_webaction(
            WebactionContext(
                identifier,
                event["project_name"],
                event["folder_id"],
                event["task_id"],
                event["addon_name"],
                event["addon_version"],
            ),
            event["action_label"],
            form_data,
        )

    def _set_row_height(self, rows):
        self.setMinimumHeight(rows * 75)

    def _on_model_refresh(self):
        self._proxy_model.sort(0)
        # Force repaint all items
        viewport = self._view.viewport()
        viewport.update()

    def _on_animation(self):
        time_now = time.time()
        for action_id in tuple(self._animated_items):
            item = self._model.get_item_by_id(action_id)
            if item is None:
                self._animated_items.discard(action_id)
                continue

            start_time = item.data(ANIMATION_START_ROLE)
            if start_time is None or (time_now - start_time) > ANIMATION_LEN:
                item.setData(0, ANIMATION_STATE_ROLE)
                self._animated_items.discard(action_id)

        if not self._animated_items:
            self._animation_timer.stop()

        self.update()

    def _start_animation(self, index):
        # Offset refresh timout
        model_index = self._proxy_model.mapToSource(index)
        if not model_index.isValid():
            return
        action_id = model_index.data(ACTION_ID_ROLE)
        self._model.setData(model_index, time.time(), ANIMATION_START_ROLE)
        self._model.setData(model_index, 1, ANIMATION_STATE_ROLE)
        self._animated_items.add(action_id)
        self._animation_timer.start()

    def _on_clicked(self, index):
        if not index or not index.isValid():
            return

        is_group = index.data(ACTION_IS_GROUP_ROLE)
        # TODO define and store what is default action for a group
        action_id = index.data(ACTION_ID_ROLE)

        project_name = self._model.get_selected_project_name()
        folder_id = self._model.get_selected_folder_id()
        task_id = self._model.get_selected_task_id()

        action_type = index.data(ACTION_TYPE_ROLE)
        if action_type == "webaction":
            action_item = self._model.get_action_item_by_id(action_id)
            context = WebactionContext(
                action_id,
                project_name,
                folder_id,
                task_id,
                action_item.addon_name,
                action_item.addon_version
            )
            self._controller.trigger_webaction(
                context, action_item.full_label
            )
        else:
            self._controller.trigger_action(
                action_id, project_name, folder_id, task_id
            )

        self._start_animation(index)

    def _show_config_dialog(self, action_id):
        action_item = self._model.get_action_item_by_id(action_id)
        config_fields = self._model.get_action_config_fields(action_id)
        if not config_fields:
            return

        project_name = self._model.get_selected_project_name()
        folder_id = self._model.get_selected_folder_id()
        task_id = self._model.get_selected_task_id()
        context = WebactionContext(
            action_id,
            project_name=project_name,
            folder_id=folder_id,
            task_id=task_id,
            addon_name=action_item.addon_name,
            addon_version=action_item.addon_version,
        )
        values = self._controller.get_action_config_values(context)

        dialog = self._create_attrs_dialog(
            config_fields,
            "Action Config",
            "Save",
            "Cancel",
        )
        dialog.set_values(values)
        result = dialog.exec_()
        if result == QtWidgets.QDialog.Accepted:
            new_values = dialog.get_values()
            self._controller.set_action_config_values(context, new_values)

    def _create_attrs_dialog(
        self,
        config_fields,
        title,
        submit_label,
        cancel_label,
        submit_icon=None,
        cancel_icon=None,
    ):
        """Creates attribute definitions dialog.

        Types:
            label - 'text'
            text - 'label', 'value', 'placeholder', 'regex',
                'multiline', 'syntax'
            boolean - 'label', 'value'
            select - 'label', 'value', 'options'
            multiselect - 'label', 'value', 'options'
            hidden - 'value'
            integer - 'label', 'value', 'placeholder', 'min', 'max'
            float - 'label', 'value', 'placeholder', 'min', 'max'

        """
        attr_defs = []
        for config_field in config_fields:
            field_type = config_field["type"]
            attr_def = None
            if field_type == "label":
                label = config_field.get("value")
                if label is None:
                    label = config_field.get("text")
                attr_def = UILabelDef(
                    label, key=uuid.uuid4().hex
                )
            elif field_type == "boolean":
                value = config_field["value"]
                if isinstance(value, str):
                    value = value.lower() == "true"

                attr_def = BoolDef(
                    config_field["name"],
                    default=value,
                    label=config_field.get("label"),
                )
            elif field_type == "text":
                attr_def = TextDef(
                    config_field["name"],
                    default=config_field.get("value"),
                    label=config_field.get("label"),
                    placeholder=config_field.get("placeholder"),
                    multiline=config_field.get("multiline", False),
                    regex=config_field.get("regex"),
                    # syntax=config_field["syntax"],
                )
            elif field_type in ("integer", "float"):
                value = config_field.get("value")
                if isinstance(value, str):
                    if field_type == "integer":
                        value = int(value)
                    else:
                        value = float(value)
                attr_def = NumberDef(
                    config_field["name"],
                    default=value,
                    label=config_field.get("label"),
                    decimals=0 if field_type == "integer" else 5,
                    # placeholder=config_field.get("placeholder"),
                    minimum=config_field.get("min"),
                    maximum=config_field.get("max"),
                )
            elif field_type in ("select", "multiselect"):
                attr_def = EnumDef(
                    config_field["name"],
                    items=config_field["options"],
                    default=config_field.get("value"),
                    label=config_field.get("label"),
                    multiselection=field_type == "multiselect",
                )
            elif field_type == "hidden":
                attr_def = HiddenDef(
                    config_field["name"],
                    default=config_field.get("value"),
                )

            if attr_def is None:
                print(f"Unknown config field type: {field_type}")
                attr_def = UILabelDef(
                    f"Unknown field type '{field_type}",
                    key=uuid.uuid4().hex
                )
            attr_defs.append(attr_def)

        dialog = AttributeDefinitionsDialog(
            attr_defs,
            title=title,
            parent=self,
        )
        if submit_label:
            dialog.set_submit_label(submit_label)
        else:
            dialog.set_submit_visible(False)

        if submit_icon:
            dialog.set_submit_icon(submit_icon)

        if cancel_label:
            dialog.set_cancel_label(cancel_label)
        else:
            dialog.set_cancel_visible(False)

        if cancel_icon:
            dialog.set_cancel_icon(cancel_icon)

        return dialog
