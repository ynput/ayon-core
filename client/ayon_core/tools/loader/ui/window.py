from __future__ import annotations

import math
from typing import Optional

from qtpy import QtWidgets, QtCore, QtGui

from ayon_core.lib.icon_definitions import MaterialSymbolsIcon
from ayon_core.resources import get_ayon_icon_filepath
from ayon_core.style import load_stylesheet
from ayon_core.pipeline.actions import LoaderActionResult
from ayon_core.tools.utils import (
    MessageOverlayObject,
    ErrorMessageBox,
    ThumbnailPainterWidget,
    RefreshButton,
    GoToCurrentButton,
    ProjectsCombobox,
    get_qt_icon,
    FoldersFiltersWidget,
)
from ayon_core.tools.attribute_defs import AttributeDefinitionsDialog
from ayon_core.tools.utils.lib import center_window
from ayon_core.tools.common_models import StatusItem
from ayon_core.tools.loader.abstract import ProductTypeItem
from ayon_core.tools.loader.control import LoaderController

from .folders_widget import LoaderFoldersWidget
from .tasks_widget import LoaderTasksWidget
from .products_widget import ProductsWidget
from .product_group_dialog import ProductGroupDialog
from .info_widget import InfoWidget
from .repres_widget import RepresentationsWidget
from .search_bar import FiltersBar, FilterDefinition

FIND_KEY_SEQUENCE = QtGui.QKeySequence(
    QtCore.Qt.Modifier.CTRL | QtCore.Qt.Key_F
)
GROUP_KEY_SEQUENCE = QtGui.QKeySequence(
    QtCore.Qt.Modifier.CTRL | QtCore.Qt.Key_G
)


class LoadErrorMessageBox(ErrorMessageBox):
    def __init__(self, messages, parent=None):
        self._messages = messages
        super().__init__("Loading failed", parent)

    def _create_top_widget(self, parent_widget):
        label_widget = QtWidgets.QLabel(parent_widget)
        label_widget.setText(
            "<span style='font-size:18pt;'>Failed to load items</span>"
        )
        return label_widget

    def _get_report_data(self):
        report_data = []
        for exc_msg, tb_text, repre, product, version in self._messages:
            report_message = (
                "During load error happened on Product: \"{product}\""
                " Representation: \"{repre}\" Version: {version}"
                "\n\nError message: {message}"
            ).format(
                product=product,
                repre=repre,
                version=version,
                message=exc_msg
            )
            if tb_text:
                report_message += "\n\n{}".format(tb_text)
            report_data.append(report_message)
        return report_data

    def _create_content(self, content_layout):
        item_name_template = (
            "<span style='font-weight:bold;'>Product:</span> {}<br>"
            "<span style='font-weight:bold;'>Version:</span> {}<br>"
            "<span style='font-weight:bold;'>Representation:</span> {}<br>"
        )
        exc_msg_template = "<span style='font-weight:bold'>{}</span>"

        for exc_msg, tb_text, repre, product, version in self._messages:
            line = self._create_line()
            content_layout.addWidget(line)

            item_name = item_name_template.format(product, version, repre)
            item_name_widget = QtWidgets.QLabel(
                item_name.replace("\n", "<br>"), self
            )
            item_name_widget.setWordWrap(True)
            content_layout.addWidget(item_name_widget)

            exc_msg = exc_msg_template.format(exc_msg.replace("\n", "<br>"))
            message_label_widget = QtWidgets.QLabel(exc_msg, self)
            message_label_widget.setWordWrap(True)
            content_layout.addWidget(message_label_widget)

            if tb_text:
                line = self._create_line()
                tb_widget = self._create_traceback_widget(tb_text, self)
                content_layout.addWidget(line)
                content_layout.addWidget(tb_widget)


class RefreshHandler:
    def __init__(self):
        self._project_refreshed = False
        self._folders_refreshed = False
        self._products_refreshed = False

    @property
    def project_refreshed(self):
        return self._products_refreshed

    @property
    def folders_refreshed(self):
        return self._folders_refreshed

    @property
    def products_refreshed(self):
        return self._products_refreshed

    def reset(self):
        self._project_refreshed = False
        self._folders_refreshed = False
        self._products_refreshed = False

    def set_project_refreshed(self):
        self._project_refreshed = True

    def set_folders_refreshed(self):
        self._folders_refreshed = True

    def set_products_refreshed(self):
        self._products_refreshed = True


class AYONLogoAnimation(QtWidgets.QWidget):
    """Animated AYON 'Y' symbol (three bars and a dot).

    The dot bounces and while it is in the air the bars rotate by
        120 degrees, so on landing the symbol looks the same as at
        the start. Symbol is scaled to fit the widget size.

    Animation runs only while the widget is visible and active.

    """
    # Proportions of the 'Y' symbol relative to the bar length,
    #   taken from the AYON logo
    _bar_width_ratio: float = 0.277
    # Gap between center of the symbol and the inner end of a bar
    _bar_gap_ratio: float = 0.315
    _dot_radius_ratio: float = 0.273
    _dot_distance_ratio: float = 1.05
    # How high the dot jumps
    _jump_ratio: float = 1.0
    # Extents of the animated symbol from its center
    _top_extent_ratio: float = (
        _dot_distance_ratio + _dot_radius_ratio + _jump_ratio
    )
    _bottom_extent_ratio: float = _bar_gap_ratio + 1.0
    # Width of the symbol (rotated bars)
    _width_ratio: float = (_bar_gap_ratio + 1.0) * 2

    _anim_duration: int = 1400
    # Animation timeline (normalized 0.0 - 1.0)
    _jump_start: float = 0.1
    _jump_peak: float = 0.5
    _jump_end: float = 0.85
    _rotation_start: float = 0.15
    _rotation_end: float = 0.75

    _bars_color = QtGui.QColor(154, 169, 183)
    _dot_color = QtGui.QColor(0, 215, 160)
    _dot_inactive_color = QtGui.QColor(220, 90, 90)

    def __init__(self, parent=None, bar_length: int = 44):
        super().__init__(parent)

        anim = QtCore.QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(self._anim_duration)
        anim.setLoopCount(-1)
        anim.valueChanged.connect(self._on_anim_value)

        self._anim = anim
        self._progress: float = 0.0
        self._ease_out = QtCore.QEasingCurve(QtCore.QEasingCurve.OutQuad)
        self._ease_in = QtCore.QEasingCurve(QtCore.QEasingCurve.InQuad)
        self._ease_in_out = QtCore.QEasingCurve(
            QtCore.QEasingCurve.InOutCubic
        )
        self._bar_length: int = bar_length
        self._active: bool = True

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred,
            QtWidgets.QSizePolicy.Preferred,
        )

    def sizeHint(self):
        height_ratio = self._top_extent_ratio + self._bottom_extent_ratio
        return QtCore.QSize(
            math.ceil(self._bar_length * self._width_ratio),
            math.ceil(self._bar_length * height_ratio),
        )

    def minimumSizeHint(self):
        return QtCore.QSize(0, 0)

    def set_active(self, active: bool):
        """Inactive symbol does not animate and has red dot."""
        if self._active == active:
            return
        self._active = active
        self._update_animation()
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self._update_animation()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._update_animation()

    def _update_animation(self):
        should_run = self.isVisible() and self._active
        is_running = (
            self._anim.state() == QtCore.QAbstractAnimation.Running
        )
        if should_run:
            if not is_running:
                self._anim.start()
            return

        if is_running:
            self._anim.stop()
        # Show the symbol in its rest pose
        self._progress = 0.0

    def _on_anim_value(self, value):
        self._progress = float(value)
        self.update()

    def _get_anim_values(self) -> tuple[float, float, float, float]:
        """Values of animation for current progress.

        Returns:
            tuple[float, float, float, float]: Jump height ratio (0.0-1.0),
                bars rotation in degrees, symbol scale and dot squash.

        """
        progress = self._progress

        # Dot jump
        jump = 0.0
        if self._jump_start <= progress < self._jump_peak:
            value = (
                (progress - self._jump_start)
                / (self._jump_peak - self._jump_start)
            )
            jump = self._ease_out.valueForProgress(value)
        elif self._jump_peak <= progress < self._jump_end:
            value = (
                (progress - self._jump_peak)
                / (self._jump_end - self._jump_peak)
            )
            jump = 1.0 - self._ease_in.valueForProgress(value)

        # Bars rotation, rotation by 120 degrees looks the same as
        #   no rotation
        rotation = 0.0
        if self._rotation_start < progress < self._rotation_end:
            value = (
                (progress - self._rotation_start)
                / (self._rotation_end - self._rotation_start)
            )
            rotation = 120.0 * self._ease_in_out.valueForProgress(value)

        # Symbol squashes before jump (takeoff) and after landing
        squash = 0.0
        if progress < self._jump_start:
            squash = math.sin(progress / self._jump_start * math.pi)
        elif progress >= self._jump_end:
            value = (progress - self._jump_end) / (1.0 - self._jump_end)
            squash = math.sin(value * math.pi)
        scale = 1.0 - (0.08 * squash)

        return jump, rotation, scale, squash

    def paintEvent(self, event):
        rect = self.rect()
        height_ratio = self._top_extent_ratio + self._bottom_extent_ratio
        bar_length = min(
            float(self._bar_length),
            rect.height() / height_ratio,
            rect.width() / self._width_ratio,
        )
        if bar_length < 4:
            return

        jump, rotation, scale, squash = self._get_anim_values()

        bar_width = bar_length * self._bar_width_ratio
        bar_gap = bar_length * self._bar_gap_ratio
        dot_radius = bar_length * self._dot_radius_ratio
        bottom_offset = bar_length * self._bottom_extent_ratio

        # Center the symbol in the widget
        content_height = bar_length * height_ratio
        center = QtCore.QPointF(
            rect.center().x(),
            (
                rect.y()
                + (rect.height() - content_height) * 0.5
                + bar_length * self._top_extent_ratio
            ),
        )

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtCore.Qt.NoPen)
        painter.translate(center)

        # Bars, squash is anchored to the bottom of the symbol
        painter.save()
        painter.translate(0, bottom_offset)
        painter.scale(1.0 + (1.0 - scale), scale)
        painter.translate(0, -bottom_offset)
        painter.rotate(rotation)
        painter.setBrush(self._bars_color)
        # Bar pointing down, other two are rotated by 120 degrees
        bar_rect = QtCore.QRectF(
            -bar_width * 0.5, bar_gap, bar_width, bar_length
        )
        for _ in range(3):
            painter.drawRect(bar_rect)
            painter.rotate(120)
        painter.restore()

        # Dot
        dot_y = -(
            bar_length * self._dot_distance_ratio
            + bar_length * self._jump_ratio * jump
        )
        # Follow the bars when they are squashed
        dot_y += bottom_offset * (1.0 - scale)
        dot_color = self._dot_color
        if not self._active:
            dot_color = self._dot_inactive_color
        painter.setBrush(dot_color)
        dot_squash = 0.15 * squash
        painter.drawEllipse(
            QtCore.QPointF(0, dot_y + dot_radius * dot_squash),
            dot_radius * (1.0 + dot_squash),
            dot_radius * (1.0 - dot_squash),
        )
        painter.end()


class ConnectionOverlay(QtWidgets.QWidget):
    """Overlay shown when connection to AYON server is lost."""
    _bg_color = QtGui.QColor(37, 42, 48, 212)

    def __init__(self, parent):
        super().__init__(parent)

        logo_widget = AYONLogoAnimation(self)

        message_label = QtWidgets.QLabel(self)
        message_label.setAlignment(QtCore.Qt.AlignCenter)
        message_label.setWordWrap(True)
        message_label.setStyleSheet(
            "font-size: 16pt; font-weight: bold; color: #ffffff;"
            " background: transparent;"
        )

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addStretch(1)
        main_layout.addWidget(logo_widget, 0, QtCore.Qt.AlignHCenter)
        main_layout.addSpacing(16)
        main_layout.addWidget(message_label, 0)
        main_layout.addStretch(1)

        self._logo_widget = logo_widget
        self._message_label = message_label

        self._server_restarting: bool = False
        self._auth_invalid: bool = False
        self._update_message()

    def set_server_restarting(self, restarting: bool):
        self._server_restarting = restarting
        self._update_message()

    def set_invalid_authentication(self, invalid: bool):
        self._auth_invalid = invalid
        self._logo_widget.set_active(not invalid)
        self._update_message()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), self._bg_color)
        painter.end()

    def _update_message(self):
        if self._auth_invalid:
            text = (
                "Authentication failed.\nPlease log in again"
                " and restart all applications."
            )
        elif self._server_restarting:
            text = "AYON server is restarting.."
        else:
            text = "Connection to AYON server lost.."
        self._message_label.setText(text)


class LoaderWindow(QtWidgets.QWidget):
    def __init__(self, controller=None, parent=None):
        super().__init__(parent)

        if controller is None:
            controller = LoaderController()

        subtitle = controller.get_window_subtitle()
        title = "AYON Loader"
        if subtitle:
            title += f" - {subtitle}"
        self.setWindowTitle(title)
        icon = QtGui.QIcon(get_ayon_icon_filepath())
        self.setWindowIcon(icon)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)

        overlay_object = MessageOverlayObject(self)

        main_splitter = QtWidgets.QSplitter(self)

        context_splitter = QtWidgets.QSplitter(main_splitter)
        context_splitter.setOrientation(QtCore.Qt.Vertical)

        # Context selection widget
        context_widget = QtWidgets.QWidget(context_splitter)

        context_top_widget = QtWidgets.QWidget(context_widget)
        projects_combobox = ProjectsCombobox(
            controller,
            context_top_widget,
            handle_expected_selection=True
        )
        projects_combobox.set_select_item_visible(True)
        projects_combobox.set_libraries_separator_visible(True)
        projects_combobox.set_standard_filter_enabled(
            controller.is_standard_projects_filter_enabled()
        )

        go_to_current_btn = GoToCurrentButton(context_top_widget)
        refresh_btn = RefreshButton(context_top_widget)

        context_top_layout = QtWidgets.QHBoxLayout(context_top_widget)
        context_top_layout.setContentsMargins(0, 0, 0, 0,)
        context_top_layout.setSpacing(4)
        context_top_layout.addWidget(projects_combobox, 1)
        context_top_layout.addWidget(go_to_current_btn, 0)
        context_top_layout.addWidget(refresh_btn, 0)

        filters_widget = FoldersFiltersWidget(context_widget)

        folders_widget = LoaderFoldersWidget(controller, context_widget)

        context_layout = QtWidgets.QVBoxLayout(context_widget)
        context_layout.setContentsMargins(0, 0, 0, 0)
        context_layout.addWidget(context_top_widget, 0)
        context_layout.addWidget(filters_widget, 0)
        context_layout.addWidget(folders_widget, 1)

        tasks_widget = LoaderTasksWidget(controller, context_widget)

        context_splitter.addWidget(context_widget)
        context_splitter.addWidget(tasks_widget)
        context_splitter.setStretchFactor(0, 65)
        context_splitter.setStretchFactor(1, 35)

        # Product + version selection item
        products_wrap_widget = QtWidgets.QWidget(main_splitter)

        products_inputs_widget = QtWidgets.QWidget(products_wrap_widget)
        search_bar = FiltersBar(products_inputs_widget)

        product_group_checkbox = QtWidgets.QCheckBox(
            "Enable grouping", products_inputs_widget)
        product_group_checkbox.setChecked(True)

        products_inputs_layout = QtWidgets.QHBoxLayout(products_inputs_widget)
        products_inputs_layout.setContentsMargins(0, 0, 0, 0)
        products_inputs_layout.addWidget(search_bar, 1)
        products_inputs_layout.addWidget(product_group_checkbox, 0)

        products_widget = ProductsWidget(controller, products_wrap_widget)

        products_wrap_layout = QtWidgets.QVBoxLayout(products_wrap_widget)
        products_wrap_layout.setContentsMargins(0, 0, 0, 0)
        products_wrap_layout.addWidget(products_inputs_widget, 0)
        products_wrap_layout.addWidget(products_widget, 1)

        right_panel_splitter = QtWidgets.QSplitter(main_splitter)
        right_panel_splitter.setOrientation(QtCore.Qt.Vertical)

        thumbnails_widget = ThumbnailPainterWidget(right_panel_splitter)
        thumbnails_widget.set_use_checkboard(False)

        info_widget = InfoWidget(controller, right_panel_splitter)

        repre_widget = RepresentationsWidget(controller, right_panel_splitter)

        right_panel_splitter.addWidget(thumbnails_widget)
        right_panel_splitter.addWidget(info_widget)
        right_panel_splitter.addWidget(repre_widget)

        right_panel_splitter.setStretchFactor(0, 1)
        right_panel_splitter.setStretchFactor(1, 1)
        right_panel_splitter.setStretchFactor(2, 2)

        main_splitter.addWidget(context_splitter)
        main_splitter.addWidget(products_wrap_widget)
        main_splitter.addWidget(right_panel_splitter)

        main_splitter.setStretchFactor(0, 4)
        main_splitter.setStretchFactor(1, 6)
        main_splitter.setStretchFactor(2, 1)

        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.addWidget(main_splitter)

        connection_overlay = ConnectionOverlay(self)
        connection_overlay.setVisible(False)

        # Server events are received in a background thread, the timer
        #   processes them in main thread
        server_events_timer = QtCore.QTimer(self)
        server_events_timer.setInterval(200)
        server_events_timer.timeout.connect(self._on_server_events_timer)

        show_timer = QtCore.QTimer()
        show_timer.setInterval(1)

        show_timer.timeout.connect(self._on_show_timer)

        projects_combobox.refreshed.connect(self._on_projects_refresh)
        folders_widget.refreshed.connect(self._on_folders_refresh)
        products_widget.refreshed.connect(self._on_products_refresh)
        filters_widget.text_changed.connect(
            self._on_folder_filter_change
        )
        filters_widget.my_tasks_changed.connect(
            self._on_my_tasks_checkbox_state_changed
        )
        search_bar.filter_changed.connect(self._on_filter_change)
        product_group_checkbox.stateChanged.connect(
            self._on_product_group_change
        )
        products_widget.merged_products_selection_changed.connect(
            self._on_merged_products_selection_change
        )
        products_widget.selection_changed.connect(
            self._on_products_selection_change
        )
        go_to_current_btn.clicked.connect(
            self._on_go_to_current_context_click
        )
        refresh_btn.clicked.connect(
            self._on_refresh_click
        )
        controller.register_event_callback(
            "load.finished",
            self._on_load_finished,
        )
        controller.register_event_callback(
            "selection.project.changed",
            self._on_project_selection_changed,
        )
        controller.register_event_callback(
            "selection.folders.changed",
            self._on_folders_selection_changed,
        )
        controller.register_event_callback(
            "selection.tasks.changed",
            self._on_tasks_selection_change,
        )
        controller.register_event_callback(
            "selection.versions.changed",
            self._on_versions_selection_changed,
        )
        controller.register_event_callback(
            "controller.reset.started",
            self._on_controller_reset_start,
        )
        controller.register_event_callback(
            "controller.reset.finished",
            self._on_controller_reset_finish,
        )
        controller.register_event_callback(
            "loader.action.finished",
            self._on_loader_action_finished,
        )
        controller.register_event_callback(
            "ayon.connection.opened",
            self._on_connection_opened,
        )
        controller.register_event_callback(
            "ayon.connection.closed",
            self._on_connection_closed,
        )
        controller.register_event_callback(
            "ayon.auth.failed",
            self._on_auth_failed,
        )
        controller.register_event_callback(
            "ayon.server.restart",
            self._on_server_restart,
        )

        self._connection_overlay = connection_overlay
        self._server_events_timer = server_events_timer
        self._overlay_object = overlay_object

        self._group_dialog = ProductGroupDialog(controller, self)

        self._main_splitter = main_splitter

        self._go_to_current_btn = go_to_current_btn
        self._refresh_btn = refresh_btn
        self._projects_combobox = projects_combobox

        self._filters_widget = filters_widget
        self._folders_widget = folders_widget

        self._tasks_widget = tasks_widget

        self._search_bar = search_bar
        self._product_group_checkbox = product_group_checkbox
        self._products_widget = products_widget

        self._right_panel_splitter = right_panel_splitter
        self._thumbnails_widget = thumbnails_widget
        self._info_widget = info_widget
        self._repre_widget = repre_widget

        self._controller = controller
        self._refresh_handler = RefreshHandler()
        self._first_show = True
        self._reset_on_show = True
        self._show_counter = 0
        self._show_timer = show_timer
        self._selected_project_name = None
        self._selected_folder_ids = set()
        self._selected_version_ids = set()

        self._set_product_type_filters = True

        self._products_widget.set_enable_grouping(
            self._product_group_checkbox.isChecked()
        )

    def refresh(self):
        self._reset_on_show = False
        self._controller.reset()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._connection_overlay.resize(self.size())

    def showEvent(self, event):
        super().showEvent(event)

        if self._first_show:
            self._on_first_show()

        self._show_timer.start()
        self._server_events_timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._server_events_timer.stop()

    def closeEvent(self, event):
        super().closeEvent(event)
        self._server_events_timer.stop()

        self._reset_on_show = True

    def keyPressEvent(self, event):
        if hasattr(event, "keyCombination"):
            combination = event.keyCombination()
        else:
            combination = QtGui.QKeySequence(event.modifiers() | event.key())
        if (
            FIND_KEY_SEQUENCE == combination
            and not event.isAutoRepeat()
        ):
            self._search_bar.show_filters_popup()
            event.setAccepted(True)
            return

        # Grouping products on pressing Ctrl + G
        if (
            GROUP_KEY_SEQUENCE == combination
            and not event.isAutoRepeat()
        ):
            self._show_group_dialog()
            event.setAccepted(True)
            return

        super().keyPressEvent(event)

    def _on_first_show(self):
        self._first_show = False
        # width, height = 1800, 900
        width, height = 1500, 750

        self.resize(width, height)

        mid_width = int(width / 1.8)
        sides_width = int((width - mid_width) * 0.5)
        self._main_splitter.setSizes(
            [sides_width, mid_width, sides_width]
        )

        thumbnail_height = int(height / 3.6)
        info_height = int((height - thumbnail_height) * 0.5)
        self._right_panel_splitter.setSizes(
            [thumbnail_height, info_height, info_height]
        )
        self.setStyleSheet(load_stylesheet())
        center_window(self)

    def _on_show_timer(self):
        if self._show_counter < 2:
            self._show_counter += 1
            return

        self._show_counter = 0
        self._show_timer.stop()

        if self._reset_on_show:
            self.refresh()

    def _show_toast_message(
        self,
        message: str,
        success: bool = True,
        message_id: Optional[str] = None,
    ):
        message_type = None
        if not success:
            message_type = "error"

        self._overlay_object.add_message(
            message, message_type, message_id=message_id
        )

    def _show_group_dialog(self):
        project_name = self._projects_combobox.get_selected_project_name()
        if not project_name:
            return

        product_ids = {
            version_info["product_id"]
            for version_info in (
                self._products_widget.get_selected_version_info()
            )
        }
        if not product_ids:
            return

        self._group_dialog.set_product_ids(
            project_name,
            self._selected_folder_ids,
            product_ids,
        )
        self._group_dialog.show()

    def _on_folder_filter_change(self, text: str) -> None:
        self._folders_widget.set_name_filter(text)

    def _on_my_tasks_checkbox_state_changed(self, enabled: bool) -> None:
        folder_ids = None
        task_ids = None
        if enabled:
            entity_ids = self._controller.get_my_tasks_entity_ids(
                self._selected_project_name
            )
            folder_ids = entity_ids["folder_ids"]
            task_ids = entity_ids["task_ids"]
        self._folders_widget.set_folder_ids_filter(folder_ids)
        self._tasks_widget.set_task_ids_filter(task_ids)

    def _on_product_group_change(self):
        self._products_widget.set_enable_grouping(
            self._product_group_checkbox.isChecked()
        )

    def _on_filter_change(self, filter_name):
        if filter_name == "product_name":
            self._products_widget.set_name_filter(
                self._search_bar.get_filter_value("product_name")
            )
        elif filter_name == "product_types":
            product_types = self._search_bar.get_filter_value("product_types")
            self._products_widget.set_product_type_filter(product_types)

        elif filter_name == "statuses":
            status_names = self._search_bar.get_filter_value("statuses")
            self._products_widget.set_statuses_filter(status_names)

        elif filter_name == "version_tags":
            version_tags = self._search_bar.get_filter_value("version_tags")
            self._products_widget.set_version_tags_filter(version_tags)

        elif filter_name == "task_tags":
            task_tags = self._search_bar.get_filter_value("task_tags")
            self._products_widget.set_task_tags_filter(task_tags)

    def _on_tasks_selection_change(self, event):
        self._products_widget.set_tasks_filter(event["task_ids"])

    def _on_merged_products_selection_change(self):
        items = self._products_widget.get_selected_merged_products()
        self._folders_widget.set_merged_products_selection(items)

    def _on_products_selection_change(self):
        items = self._products_widget.get_selected_version_info()
        self._info_widget.set_selected_version_info(
            self._projects_combobox.get_selected_project_name(),
            items
        )

    def _on_go_to_current_context_click(self):
        context = self._controller.get_current_context()
        self._controller.set_expected_selection(
            context["project_name"],
            context["folder_id"],
        )

    def _on_refresh_click(self):
        self._controller.reset()

    def _on_controller_reset_start(self):
        self._refresh_handler.reset()

    def _on_controller_reset_finish(self):
        context = self._controller.get_current_context()
        project_name = context["project_name"]
        self._go_to_current_btn.setVisible(bool(project_name))
        self._projects_combobox.set_current_context_project(project_name)
        if not self._refresh_handler.project_refreshed:
            self._projects_combobox.refresh()
        self._update_filters()
        if self._controller.get_server_connection_state() is False:
            self._on_connection_closed()
        # Update my tasks
        self._on_my_tasks_checkbox_state_changed(
            self._filters_widget.is_my_tasks_checked()
        )

    def _on_load_finished(self, event):
        error_info = event["error_info"]
        if not error_info:
            return

        box = LoadErrorMessageBox(error_info, self)
        box.show()

    def _on_loader_action_finished(self, event):
        crashed = event["crashed"]
        if crashed:
            self._show_toast_message(
                "Action failed",
                success=False,
            )
            return

        result: Optional[LoaderActionResult] = event["result"]
        if result is None:
            return

        if result.message:
            self._show_toast_message(
                result.message, result.success
            )

        if result.form is None:
            return

        form = result.form
        dialog = AttributeDefinitionsDialog(
            form.fields,
            title=form.title,
            parent=self,
        )
        if result.form_values:
            dialog.set_values(result.form_values)
        submit_label = form.submit_label
        submit_icon = form.submit_icon
        cancel_label = form.cancel_label
        cancel_icon = form.cancel_icon

        if submit_icon:
            submit_icon = get_qt_icon(submit_icon)
        if cancel_icon:
            cancel_icon = get_qt_icon(cancel_icon)

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

        dialog.setMinimumSize(300, 140)
        result = dialog.exec_()
        if result != QtWidgets.QDialog.Accepted:
            return

        form_values = dialog.get_values()
        self._controller.trigger_action_item(
            identifier=event["identifier"],
            project_name=event["project_name"],
            selected_ids=event["selected_ids"],
            selected_entity_type=event["selected_entity_type"],
            options={},
            data=event["data"],
            form_values=form_values,
        )

    def _on_project_selection_changed(self, event):
        self._selected_project_name = event["project_name"]
        self._update_filters()

    def _update_filters(self):
        project_name = self._selected_project_name
        if not project_name:
            self._search_bar.set_search_items([])
            return

        product_type_items: list[ProductTypeItem] = (
            self._controller.get_product_type_items(project_name)
        )
        status_items: list[StatusItem] = (
            self._controller.get_project_status_items(project_name)
        )
        tags_by_entity_type = (
            self._controller.get_available_tags_by_entity_type(project_name)
        )
        tag_items = self._controller.get_project_anatomy_tags(project_name)
        tag_color_by_name = {
            tag_item.name: tag_item.color
            for tag_item in tag_items
        }

        filter_product_type_items = [
            {
                "value": item.name,
                "icon": item.icon,
            }
            for item in product_type_items
        ]
        filter_status_items = [
            {
                "icon": MaterialSymbolsIcon(
                    status_item.icon, color=status_item.color
                ),
                "color": status_item.color,
                "value": status_item.name,
            }
            for status_item in status_items
        ]
        version_tags = [
            {
                "value": tag_name,
                "color": tag_color_by_name.get(tag_name),
            }
            for tag_name in tags_by_entity_type.get("versions") or []
        ]
        task_tags = [
            {
                "value": tag_name,
                "color": tag_color_by_name.get(tag_name),
            }
            for tag_name in tags_by_entity_type.get("tasks") or []
        ]

        self._search_bar.set_search_items([
            FilterDefinition(
                name="product_name",
                title="Product name",
                filter_type="text",
                icon=None,
                placeholder="Product name filter...",
                items=None,
            ),
            FilterDefinition(
                name="product_types",
                title="Product type",
                filter_type="list",
                icon=None,
                items=filter_product_type_items,
            ),
            FilterDefinition(
                name="statuses",
                title="Statuses",
                filter_type="list",
                icon=None,
                items=filter_status_items,
            ),
            FilterDefinition(
                name="version_tags",
                title="Version tags",
                filter_type="list",
                icon=None,
                items=version_tags,
            ),
            FilterDefinition(
                name="task_tags",
                title="Task tags",
                filter_type="list",
                icon=None,
                items=task_tags,
            ),
        ])

        # Set product types filter from settings
        if self._set_product_type_filters:
            self._set_product_type_filters = False
            product_types_filter = self._controller.get_product_types_filter()
            product_types = []
            for item in filter_product_type_items:
                product_type = item["value"]
                matching = (
                    int(product_type in product_types_filter.product_types)
                    + int(product_types_filter.is_allow_list)
                )
                if matching % 2 == 0:
                    product_types.append(product_type)

            if (
                product_types
                and len(product_types) < len(filter_product_type_items)
            ):
                self._search_bar.set_filter_value(
                    "product_types",
                    product_types
                )

    def _on_folders_selection_changed(self, event):
        self._selected_folder_ids = set(event["folder_ids"])
        self._update_thumbnails()

    def _on_versions_selection_changed(self, event):
        self._selected_version_ids = set(event["version_ids"])
        self._update_thumbnails()

    def _update_thumbnails(self):
        # TODO make this threaded and show loading animation while running
        project_name = self._selected_project_name
        entity_type = None
        entity_ids = set()
        if self._selected_version_ids:
            entity_ids = set(self._selected_version_ids)
            entity_type = "version"
        elif self._selected_folder_ids:
            entity_ids = set(self._selected_folder_ids)
            entity_type = "folder"

        thumbnail_path_by_entity_id = self._controller.get_thumbnail_paths(
            project_name, entity_type, entity_ids
        )
        thumbnail_paths = set(thumbnail_path_by_entity_id.values())
        thumbnail_paths.discard(None)

        if thumbnail_paths:
            self._thumbnails_widget.set_current_thumbnail_paths(
                thumbnail_paths
            )
        else:
            self._thumbnails_widget.set_current_thumbnails(None)

    def _on_projects_refresh(self):
        self._refresh_handler.set_project_refreshed()
        if not self._refresh_handler.folders_refreshed:
            self._folders_widget.refresh()

    def _on_folders_refresh(self):
        self._refresh_handler.set_folders_refreshed()
        if not self._refresh_handler.products_refreshed:
            self._products_widget.refresh()

    def _on_products_refresh(self):
        self._refresh_handler.set_products_refreshed()

    def _on_server_events_timer(self):
        self._controller.process_server_events()

    def _on_connection_opened(self):
        self._connection_overlay.setVisible(False)
        self._connection_overlay.set_invalid_authentication(False)
        self._connection_overlay.set_server_restarting(False)

    def _on_connection_closed(self):
        self._connection_overlay.setVisible(True)

    def _on_auth_failed(self):
        self._connection_overlay.setVisible(True)
        self._connection_overlay.set_invalid_authentication(True)

    def _on_server_restart(self):
        self._connection_overlay.setVisible(True)
        self._connection_overlay.set_server_restarting(True)
