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
from ayon_core.tools.utils import (
    get_qt_icon,
)
from ayon_core.tools.attribute_defs import AttributeDefinitionsDialog
from ayon_core.tools.launcher.abstract import WebactionContext

ANIMATION_LEN = 7
SHADOW_FRAME_MARGINS = (1, 1, 1, 1)

ACTION_ID_ROLE = QtCore.Qt.UserRole + 1
ACTION_TYPE_ROLE = QtCore.Qt.UserRole + 2
ACTION_IS_GROUP_ROLE = QtCore.Qt.UserRole + 3
ACTION_HAS_CONFIGS_ROLE = QtCore.Qt.UserRole + 4
ACTION_SORT_ROLE = QtCore.Qt.UserRole + 5
ACTION_ADDON_NAME_ROLE = QtCore.Qt.UserRole + 6
ACTION_ADDON_VERSION_ROLE = QtCore.Qt.UserRole + 7
PLACEHOLDER_ITEM_ROLE = QtCore.Qt.UserRole + 8
ANIMATION_START_ROLE = QtCore.Qt.UserRole + 9
ANIMATION_STATE_ROLE = QtCore.Qt.UserRole + 10


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
class LauncherSettingsLabel(QtWidgets.QWidget):
    _settings_icon = None

    @classmethod
    def _get_settings_icon(cls):
        if cls._settings_icon is None:
            cls._settings_icon = get_qt_icon({
                "type": "material-symbols",
                "name": "settings",
            })
        return cls._settings_icon

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)

        painter.setRenderHints(
            QtGui.QPainter.Antialiasing
            | QtGui.QPainter.SmoothPixmapTransform
        )

        rect = event.rect()
        size = min(rect.height(), rect.width())
        pix_rect = QtCore.QRect(
            rect.x(), rect.y(),
            size, size
        )
        pix = self._get_settings_icon().pixmap(size, size)
        painter.drawPixmap(pix_rect, pix)

        painter.end()


class ActionOverlayWidget(QtWidgets.QFrame):
    def __init__(self, item_id, parent):
        super().__init__(parent)
        self._item_id = item_id

        settings_icon = LauncherSettingsLabel(self)
        settings_icon.setToolTip("Right click for options")
        settings_icon.setVisible(False)

        main_layout = QtWidgets.QGridLayout(self)
        main_layout.setContentsMargins(5, 5, 0, 0)
        main_layout.addWidget(settings_icon, 0, 0)
        main_layout.setColumnStretch(0, 1)
        main_layout.setColumnStretch(1, 5)

        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        self._settings_icon = settings_icon

    def enterEvent(self, event):
        super().enterEvent(event)
        self._settings_icon.setVisible(True)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._settings_icon.setVisible(False)


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

    def get_index_by_id(self, action_id):
        item = self.get_item_by_id(action_id)
        if item is not None:
            return self.indexFromItem(item)
        return QtCore.QModelIndex()

    def get_group_item_by_action_id(self, action_id):
        item = self._items_by_id.get(action_id)
        if item is not None:
            return item

        for group_id, items in self._groups_by_id.items():
            for item in items:
                if item.identifier == action_id:
                    return self._items_by_id[group_id]
        return None

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
                has_configs = False
                label = action_item.label
            else:
                label = action_item.full_label
                has_configs = bool(action_item.config_fields)

            item = self._items_by_id.get(action_item.identifier)
            if item is None:
                item = QtGui.QStandardItem()
                item.setData(action_item.identifier, ACTION_ID_ROLE)
                new_items.append(item)

            item.setFlags(QtCore.Qt.ItemIsEnabled)
            item.setData(label, QtCore.Qt.DisplayRole)
            # item.setData(label, QtCore.Qt.ToolTipRole)
            item.setData(icon, QtCore.Qt.DecorationRole)
            item.setData(is_group, ACTION_IS_GROUP_ROLE)
            item.setData(has_configs, ACTION_HAS_CONFIGS_ROLE)
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


class ActionMenuPopupModel(QtGui.QStandardItemModel):
    def set_action_items(self, action_items):
        """Set action items for the popup."""
        root_item = self.invisibleRootItem()
        root_item.removeRows(0, root_item.rowCount())

        transparent_icon = {"type": "transparent", "size": 256}
        new_items = []
        for action_item in action_items:
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

            item = QtGui.QStandardItem()
            item.setFlags(QtCore.Qt.ItemIsEnabled)
            # item.setData(action_item.full_label, QtCore.Qt.ToolTipRole)
            item.setData(action_item.full_label, QtCore.Qt.DisplayRole)
            item.setData(icon, QtCore.Qt.DecorationRole)
            item.setData(action_item.identifier, ACTION_ID_ROLE)
            item.setData(
                bool(action_item.config_fields),
                ACTION_HAS_CONFIGS_ROLE
            )
            item.setData(action_item.order, ACTION_SORT_ROLE)

            new_items.append(item)

        if new_items:
            root_item.appendRows(new_items)

    def fill_to_count(self, count: int):
        """Fill up items to specifi counter.

        This is needed to visually organize structure or the viewed items. If
            items are shown right to left then mouse would not hover over
            last item i there are multiple rows that are uneven. This will
            fill the "first items" with invisible items so visually it looks
            correct.

        Visually it will cause this:
        [ ] [ ] [ ] [A]
        [A] [A] [A] [A]

        Instead of:
        [A] [A] [A] [A]
        [A] [ ] [ ] [ ]

        """
        remainders = count - self.rowCount()
        if not remainders:
            return

        items = []
        for _ in range(remainders):
            item = QtGui.QStandardItem()
            item.setFlags(QtCore.Qt.NoItemFlags)
            item.setData(True, PLACEHOLDER_ITEM_ROLE)
            items.append(item)

        root_item = self.invisibleRootItem()
        root_item.appendRows(items)


class ActionMenuPopup(QtWidgets.QWidget):
    action_triggered = QtCore.Signal(str)
    config_requested = QtCore.Signal(str, QtCore.QPoint)

    def __init__(self, parent):
        super().__init__(parent)

        self.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        # Close widget if is not updated by event
        close_timer = QtCore.QTimer()
        close_timer.setSingleShot(True)
        close_timer.setInterval(100)

        expand_anim = QtCore.QVariantAnimation()
        expand_anim.setDuration(60)
        expand_anim.setEasingCurve(QtCore.QEasingCurve.InOutQuad)

        sh_l, sh_t, sh_r, sh_b = SHADOW_FRAME_MARGINS

        # View with actions
        view = ActionsView(self)
        view.setGridSize(QtCore.QSize(75, 80))
        view.setIconSize(QtCore.QSize(32, 32))
        view.move(QtCore.QPoint(sh_l, sh_t))

        # Background draw
        bg_frame = QtWidgets.QFrame(self)
        bg_frame.setObjectName("ShadowFrame")
        bg_frame.stackUnder(view)

        wrapper = QtWidgets.QFrame(self)
        wrapper.setObjectName("Wrapper")

        effect = QtWidgets.QGraphicsBlurEffect(wrapper)
        effect.setBlurRadius(3.0)
        wrapper.setGraphicsEffect(effect)

        bg_layout = QtWidgets.QVBoxLayout(bg_frame)
        bg_layout.setContentsMargins(sh_l, sh_t, sh_r, sh_b)
        bg_layout.addWidget(wrapper)

        model = ActionMenuPopupModel()
        proxy_model = ActionsProxyModel()
        proxy_model.setSourceModel(model)

        view.setModel(proxy_model)
        view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        close_timer.timeout.connect(self.close)
        expand_anim.valueChanged.connect(self._on_expand_anim)
        expand_anim.finished.connect(self._on_expand_finish)

        view.clicked.connect(self._on_clicked)
        view.config_requested.connect(self._on_configs_trigger)

        self._view = view
        self._bg_frame = bg_frame
        self._effect = effect
        self._model = model
        self._proxy_model = proxy_model

        self._close_timer = close_timer
        self._expand_anim = expand_anim

        self._showed = False
        self._current_id = None
        self._right_to_left = False

    def showEvent(self, event):
        self._showed = True
        super().showEvent(event)

    def closeEvent(self, event):
        self._showed = False
        super().closeEvent(event)

    def enterEvent(self, event):
        super().leaveEvent(event)
        self._close_timer.stop()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._close_timer.start()

    def show_items(self, action_id, action_items, pos):
        if not action_items:
            if self._showed:
                self._close_timer.start()
            self._current_id = None
            return

        self._close_timer.stop()

        update_position = False
        if action_id != self._current_id:
            update_position = True
            self._current_id = action_id
            self._update_items(action_items)

        # Make sure is visible
        if not self._showed:
            update_position = True
            self.show()

        if not update_position:
            self.raise_()
            return

        # Set geometry to position
        # - first make sure widget changes from '_update_items'
        #   are recalculated
        app = QtWidgets.QApplication.instance()
        app.processEvents()
        items_count, size, target_size = self._get_size_hint()
        self._model.fill_to_count(items_count)

        window = self.screen()
        window_geo = window.geometry()
        right_to_left = (
            pos.x() + target_size.width() > window_geo.right()
            or pos.y() + target_size.height() > window_geo.bottom()
        )

        sh_l, sh_t, sh_r, sh_b = SHADOW_FRAME_MARGINS
        viewport_offset = self._view.viewport().geometry().topLeft()
        pos_x = pos.x() - (sh_l + viewport_offset.x() + 2)
        pos_y = pos.y() - (sh_t + viewport_offset.y() + 1)

        bg_x = bg_y = 0
        sort_order = QtCore.Qt.DescendingOrder
        if right_to_left:
            sort_order = QtCore.Qt.AscendingOrder
            size_diff = target_size - size
            pos_x -= size_diff.width()
            pos_y -= size_diff.height()
            bg_x = size_diff.width()
            bg_y = size_diff.height()

        bg_geo = QtCore.QRect(
            bg_x, bg_y, size.width(), size.height()
        )
        if self._expand_anim.state() == QtCore.QAbstractAnimation.Running:
            self._expand_anim.stop()
        self._first_anim_frame = True
        self._right_to_left = right_to_left

        self._proxy_model.sort(0, sort_order)
        self.setUpdatesEnabled(False)
        self._view.setMask(bg_geo.adjusted(sh_l, sh_t, -sh_r, -sh_b))
        self._view.setMinimumWidth(target_size.width())
        self._view.setMaximumWidth(target_size.width())
        self._view.setMinimumHeight(target_size.height())
        self._bg_frame.setGeometry(bg_geo)
        self.setGeometry(
            pos_x, pos_y,
            target_size.width(), target_size.height()
        )
        self.setUpdatesEnabled(True)
        self._expand_anim.updateCurrentTime(0)
        self._expand_anim.setStartValue(size)
        self._expand_anim.setEndValue(target_size)
        self._expand_anim.start()

        self.raise_()

    def _on_clicked(self, index):
        if not index or not index.isValid():
            return

        if not index.data(ACTION_HAS_CONFIGS_ROLE):
            return

        action_id = index.data(ACTION_ID_ROLE)
        self.action_triggered.emit(action_id)

    def _on_expand_anim(self, value):
        if not self._showed:
            if self._expand_anim.state() == QtCore.QAbstractAnimation.Running:
                self._expand_anim.stop()
            return

        bg_geo = self._bg_frame.geometry()
        bg_geo.setWidth(value.width())
        bg_geo.setHeight(value.height())

        if self._right_to_left:
            geo = self.geometry()
            pos = QtCore.QPoint(
                geo.width() - value.width(),
                geo.height() - value.height(),
            )
            bg_geo.setTopLeft(pos)

        sh_l, sh_t, sh_r, sh_b = SHADOW_FRAME_MARGINS
        self._view.setMask(bg_geo.adjusted(sh_l, sh_t, -sh_r, -sh_b))
        self._bg_frame.setGeometry(bg_geo)

    def _on_expand_finish(self):
        # Make sure that size is recalculated if src and targe size is same
        _, _, size = self._get_size_hint()
        self._on_expand_anim(size)

    def _get_size_hint(self):
        grid_size = self._view.gridSize()
        row_count = self._proxy_model.rowCount()
        cols = 4
        rows = 1
        while True:
            rows = row_count // cols
            if row_count % cols:
                rows += 1
            if rows <= cols:
                break
            cols += 1

        if rows == 1:
            cols = row_count

        viewport_geo = self._view.viewport().geometry()
        viewport_offset = viewport_geo.topLeft()
        # QUESTION how to get the bottom and right margins from Qt?
        vp_lr = viewport_offset.x()
        vp_tb = viewport_offset.y()
        m_l, m_t, m_r, m_b = (
            s_m + vp_m
            for s_m, vp_m in zip(
                SHADOW_FRAME_MARGINS,
                (vp_lr, vp_tb, vp_lr, vp_tb)
            )
        )
        single_width = (
            grid_size.width()
            + self._view.horizontalOffset() + m_l + m_r + 1
        )
        single_height = (
            grid_size.height()
            + self._view.verticalOffset() + m_b + m_t + 1
        )
        total_width = single_width
        total_height = single_height
        if cols > 1:
            total_width += (
                (cols - 1) * (self._view.spacing() + grid_size.width())
            )

        if rows > 1:
            total_height += (
                (rows - 1) * (grid_size.height() + self._view.spacing())
            )
        return (
            cols * rows,
            QtCore.QSize(single_width, single_height),
            QtCore.QSize(total_width, total_height)
        )

    def _update_items(self, action_items):
        """Update items in the tooltip."""
        # This method can be used to update the content of the tooltip
        # with new icon, text and settings button visibility.
        self._model.set_action_items(action_items)
        self._view.update_on_refresh()

    def _on_trigger(self, action_id):
        self.action_triggered.emit(action_id)
        self.close()

    def _on_configs_trigger(self, action_id, center_pos):
        self.config_requested.emit(action_id, center_pos)
        self.close()


class ActionDelegate(QtWidgets.QStyledItemDelegate):
    _extender_icon = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._anim_start_color = QtGui.QColor(178, 255, 246)
        self._anim_end_color = QtGui.QColor(5, 44, 50)

    def sizeHint(self, option, index):
        return option.widget.gridSize()

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)

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
    def _get_extender_pixmap(cls):
        if cls._extender_icon is None:
            cls._extender_icon = get_qt_icon({
                "type": "material-symbols",
                "name": "more_horiz",
            })
        return cls._extender_icon

    def paint(self, painter, option, index):
        painter.setRenderHints(
            QtGui.QPainter.Antialiasing
            | QtGui.QPainter.TextAntialiasing
            | QtGui.QPainter.SmoothPixmapTransform
        )

        if index.data(ANIMATION_STATE_ROLE):
            self._draw_animation(painter, option, index)
        option.displayAlignment = QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop
        super().paint(painter, option, index)

        if not index.data(ACTION_IS_GROUP_ROLE):
            return

        grid_size = option.widget.gridSize()

        extender_rect = option.rect.adjusted(5, 5, 0, 0)
        extender_size = grid_size.width() // 6
        extender_rect.setWidth(extender_size)
        extender_rect.setHeight(extender_size)

        icon = self._get_extender_pixmap()
        pix = icon.pixmap(extender_size, extender_size)
        painter.drawPixmap(extender_rect, pix)


class ActionsProxyModel(QtCore.QSortFilterProxyModel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setSortCaseSensitivity(QtCore.Qt.CaseInsensitive)

    def lessThan(self, left, right):
        if left.data(PLACEHOLDER_ITEM_ROLE):
            return True
        if right.data(PLACEHOLDER_ITEM_ROLE):
            return False

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
    config_requested = QtCore.Signal(str, QtCore.QPoint)

    def __init__(self, parent):
        super().__init__(parent)
        self.setViewMode(QtWidgets.QListView.IconMode)
        self.setResizeMode(QtWidgets.QListView.Adjust)
        self.setSelectionMode(QtWidgets.QListView.NoSelection)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setContentsMargins(0, 0, 0, 0)
        self.setViewportMargins(0, 0, 0, 0)
        self.setWrapping(True)
        self.setSpacing(0)
        self.setWordWrap(True)
        self.setMouseTracking(True)

        vertical_scroll = self.verticalScrollBar()
        vertical_scroll.setSingleStep(8)

        delegate = ActionDelegate(self)
        self.setItemDelegate(delegate)

        # Make view flickable
        flick = FlickCharm(parent=self)
        flick.activateOn(self)

        self.customContextMenuRequested.connect(self._on_context_menu)

        self._overlay_widgets = []
        self._flick = flick
        self._delegate = delegate

    def _on_context_menu(self, point):
        """Creates menu to force skip opening last workfile."""
        index = self.indexAt(point)
        if not index.isValid():
            return
        action_id = index.data(ACTION_ID_ROLE)
        rect = self.visualRect(index)
        global_center = self.mapToGlobal(rect.center())
        self.config_requested.emit(action_id, global_center)

    def update_on_refresh(self):
        viewport = self.viewport()
        viewport.update()
        self._add_overlay_widgets()

    def _add_overlay_widgets(self):
        overlay_widgets = []
        viewport = self.viewport()
        model = self.model()
        for row in range(model.rowCount()):
            index = model.index(row, 0)
            has_configs = index.data(ACTION_HAS_CONFIGS_ROLE)
            widget = None
            if has_configs:
                item_id = index.data(ACTION_ID_ROLE)
                widget = ActionOverlayWidget(item_id, viewport)
                overlay_widgets.append(widget)
            self.setIndexWidget(index, widget)

        while self._overlay_widgets:
            widget = self._overlay_widgets.pop(0)
            widget.setVisible(False)
            widget.setParent(None)
            widget.deleteLater()

        self._overlay_widgets = overlay_widgets


class ActionsWidget(QtWidgets.QWidget):
    def __init__(self, controller, parent):
        super().__init__(parent)

        self._controller = controller

        view = ActionsView(self)
        view.setGridSize(QtCore.QSize(70, 75))
        view.setIconSize(QtCore.QSize(30, 30))

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
        view.config_requested.connect(self._show_config_dialog)
        model.refreshed.connect(self._on_model_refresh)

        self._animated_items = set()
        self._animation_timer = animation_timer

        self._view = view
        self._model = model
        self._proxy_model = proxy_model

        self._popup_widget = None

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
        self._view.update_on_refresh()

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
        if is_group:
            self._show_group_popup(index)
        else:
            self._trigger_action(action_id, index)

    def _get_popup_widget(self):
        if self._popup_widget is None:
            popup_widget = ActionMenuPopup(self)

            popup_widget.action_triggered.connect(self._trigger_action)
            popup_widget.config_requested.connect(self._show_config_dialog)
            self._popup_widget = popup_widget
        return self._popup_widget

    def _show_group_popup(self, index):
        action_id = index.data(ACTION_ID_ROLE)
        action_items = self._model.get_group_items(action_id)
        rect = self._view.visualRect(index)
        pos = self.mapToGlobal(rect.topLeft())

        popup_widget = self._get_popup_widget()
        popup_widget.show_items(
            action_id, action_items, pos
        )

    def _trigger_action(self, action_id, index=None):
        project_name = self._model.get_selected_project_name()
        folder_id = self._model.get_selected_folder_id()
        task_id = self._model.get_selected_task_id()
        action_item = self._model.get_action_item_by_id(action_id)

        if action_item.action_type == "webaction":
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

        if index is None:
            item = self._model.get_group_item_by_action_id(action_id)
            if item is not None:
                index = self._proxy_model.mapFromSource(item.index())

        if index is not None:
            self._start_animation(index)

    def _show_config_dialog(self, action_id, center_point):
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
        dialog.show()
        self._center_dialog(dialog, center_point)
        result = dialog.exec_()
        if result == QtWidgets.QDialog.Accepted:
            new_values = dialog.get_values()
            self._controller.set_action_config_values(context, new_values)

    @staticmethod
    def _center_dialog(dialog, target_center_pos):
        dialog_geo = dialog.geometry()
        dialog_geo.moveCenter(target_center_pos)

        screen = dialog.screen()
        screen_geo = screen.availableGeometry()
        if screen_geo.left() > dialog_geo.left():
            dialog_geo.moveLeft(screen_geo.left())
        elif screen_geo.right() < dialog_geo.right():
            dialog_geo.moveRight(screen_geo.right())

        if screen_geo.top() > dialog_geo.top():
            dialog_geo.moveTop(screen_geo.top())
        elif screen_geo.bottom() < dialog_geo.bottom():
            dialog_geo.moveBottom(screen_geo.bottom())
        dialog.move(dialog_geo.topLeft())

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
