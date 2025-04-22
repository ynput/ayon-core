import time
import uuid
import collections

from qtpy import QtWidgets, QtCore, QtGui

from ayon_core import style
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
from ayon_core.tools.utils import get_qt_icon
from ayon_core.tools.attribute_defs import AttributeDefinitionsDialog

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
        items_by_label = collections.defaultdict(list)
        for item in items:
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
        action_items_by_id = {}
        for action_item_info in all_action_items_info:
            action_item, is_group = action_item_info
            icon_def = action_item.icon
            if not icon_def:
                icon_def = transparent_icon.copy()
            elif icon_def.get("type") == "material-symbols":
                if "name" not in icon_def:
                    icon_def = transparent_icon.copy()
                elif not icon_def.get("color"):
                    icon_def["color"] = "#f4f5f5"

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
            action_items_by_id[action_item.identifier] = action_item

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


class ActionDelegate(QtWidgets.QStyledItemDelegate):
    _cached_extender = {}

    def __init__(self, *args, **kwargs):
        super(ActionDelegate, self).__init__(*args, **kwargs)
        self._anim_start_color = QtGui.QColor(178, 255, 246)
        self._anim_end_color = QtGui.QColor(5, 44, 50)

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

        super(ActionDelegate, self).paint(painter, option, index)

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


class ActionsWidget(QtWidgets.QWidget):
    def __init__(self, controller, parent):
        super(ActionsWidget, self).__init__(parent)

        self._controller = controller

        view = QtWidgets.QListView(self)
        view.setProperty("mode", "icon")
        view.setObjectName("IconView")
        view.setViewMode(QtWidgets.QListView.IconMode)
        view.setResizeMode(QtWidgets.QListView.Adjust)
        view.setSelectionMode(QtWidgets.QListView.NoSelection)
        view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        view.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        view.setWrapping(True)
        view.setGridSize(QtCore.QSize(70, 75))
        view.setIconSize(QtCore.QSize(30, 30))
        view.setSpacing(0)
        view.setWordWrap(True)

        # Make view flickable
        flick = FlickCharm(parent=view)
        flick.activateOn(view)

        model = ActionsQtModel(controller)

        proxy_model = ActionsProxyModel()
        proxy_model.setSourceModel(model)
        view.setModel(proxy_model)

        delegate = ActionDelegate(self)
        view.setItemDelegate(delegate)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(view)

        animation_timer = QtCore.QTimer()
        animation_timer.setInterval(40)
        animation_timer.timeout.connect(self._on_animation)

        view.clicked.connect(self._on_clicked)
        view.customContextMenuRequested.connect(self._on_context_menu)
        model.refreshed.connect(self._on_model_refresh)

        self._animated_items = set()
        self._animation_timer = animation_timer

        self._flick = flick
        self._view = view
        self._model = model
        self._proxy_model = proxy_model

        self._config_widget = None

        self._set_row_height(1)

    def refresh(self):
        self._model.refresh()

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
        action_id = index.data(ACTION_ID_ROLE)

        project_name = self._model.get_selected_project_name()
        folder_id = self._model.get_selected_folder_id()
        task_id = self._model.get_selected_task_id()
        if is_group:
            action_item = self._show_menu_on_group(action_id)
            if action_item is None:
                return

            action_id = action_item.identifier
            action_label = action_item.full_label
            action_type = action_item.action_type
            addon_name = action_item.addon_name
            addon_version = action_item.addon_version
        else:
            action_label = index.data(QtCore.Qt.DisplayRole)
            action_type = index.data(ACTION_TYPE_ROLE)
            addon_name = index.data(ACTION_ADDON_NAME_ROLE)
            addon_version = index.data(ACTION_ADDON_VERSION_ROLE)

        self._controller.trigger_action(
            action_label,
            action_type,
            action_id,
            project_name,
            folder_id,
            task_id,
            addon_name,
            addon_version,
        )
        self._start_animation(index)
        self._start_animation(index)

    def _show_menu_on_group(self, action_id):
        action_items = self._model.get_group_items(action_id)

        menu = QtWidgets.QMenu(self)
        actions_mapping = {}

        for action_item in action_items:
            menu_action = QtWidgets.QAction(action_item.full_label)
            menu.addAction(menu_action)
            actions_mapping[menu_action] = action_item

        result = menu.exec_(QtGui.QCursor.pos())
        if not result:
            return None

        return actions_mapping[result]

    def _on_context_menu(self, point):
        """Creates menu to force skip opening last workfile."""
        index = self._view.indexAt(point)
        if not index.isValid():
            return

        action_id = index.data(ACTION_ID_ROLE)
        if not action_id:
            return

        config_fields = self._model.get_action_config_fields(action_id)
        if not config_fields:
            return

        values = self._controller.get_action_config_values(
            action_id,
            project_name=self._model.get_selected_project_name(),
            folder_id=self._model.get_selected_folder_id(),
            task_id=self._model.get_selected_task_id(),
            addon_name=index.data(ACTION_ADDON_NAME_ROLE),
            addon_version=index.data(ACTION_ADDON_VERSION_ROLE),
        )

        dialog = self._create_config_dialog(config_fields)
        dialog.set_values(values)
        result = dialog.exec_()
        if result == QtWidgets.QDialog.Rejected:
            return
        new_values = dialog.get_values()
        self._controller.set_action_config_values(
            action_id,
            project_name=self._model.get_selected_project_name(),
            folder_id=self._model.get_selected_folder_id(),
            task_id=self._model.get_selected_task_id(),
            addon_name=index.data(ACTION_ADDON_NAME_ROLE),
            addon_version=index.data(ACTION_ADDON_VERSION_ROLE),
            values=new_values,
        )

    def _create_config_dialog(self, config_fields):
        """Creates config widget.

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
                attr_def = UILabelDef(
                    config_field["text"], key=uuid.uuid4().hex
                )
            elif field_type == "boolean":
                attr_def = BoolDef(
                    config_field["name"],
                    default=config_field["value"],
                    label=config_field["label"],
                )
            elif field_type == "text":
                attr_def = TextDef(
                    config_field["name"],
                    default=config_field["value"],
                    label=config_field["label"],
                    placeholder=config_field["placeholder"],
                    multiline=config_field["multiline"],
                    regex=config_field["regex"],
                    # syntax=config_field["syntax"],
                )
            elif field_type in ("integer", "float"):
                attr_def = NumberDef(
                    config_field["name"],
                    default=config_field["value"],
                    label=config_field["label"],
                    decimals=0 if field_type == "integer" else 5,
                    placeholder=config_field["placeholder"],
                    min_value=config_field.get("min"),
                    max_value=config_field.get("max"),
                )
            elif field_type in ("select", "multiselect"):
                attr_def = EnumDef(
                    config_field["name"],
                    default=config_field["value"],
                    label=config_field["label"],
                    options=config_field["options"],
                    multi_select=field_type == "multiselect",
                )
            elif field_type == "hidden":
                attr_def = HiddenDef(
                    config_field["name"],
                    default=config_field["value"],
                )

            if attr_def is None:
                print(f"Unknown config field type: {field_type}")
                attr_def = UILabelDef(
                    f"Unknown field type '{field_type}",
                    key=uuid.uuid4().hex
                )
            attr_defs.append(attr_def)

        dialog = AttributeDefinitionsDialog(attr_defs, parent=self)
        dialog.setWindowTitle("Action Config")
        dialog.setStyleSheet(style.load_stylesheet())
        return dialog
