from __future__ import annotations

import os
from typing import Optional

from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.pipeline import get_current_host_name
from ayon_core.pipeline.actions import LoaderActionResult
from ayon_core.resources import get_ayon_icon_filepath
from ayon_core.style import load_stylesheet
from ayon_core.tools.attribute_defs import AttributeDefinitionsDialog
from ayon_core.tools.common_models import StatusItem
from ayon_core.tools.loader.abstract import ProductTypeItem
from ayon_core.tools.loader.control import LoaderController
from ayon_core.tools.utils import (
    ErrorMessageBox,
    GoToCurrentButton,
    MessageOverlayObject,
    PlaceholderLineEdit,
    ProjectsCombobox,
    RefreshButton,
    ThumbnailPainterWidget,
    get_qt_icon,
    restore_tool_window_state,
    save_tool_window_state,
)
from ayon_core.tools.utils.lib import center_window

from .folders_widget import LoaderFoldersWidget
from .info_widget import InfoWidget
from .product_group_dialog import ProductGroupDialog
from .products_flatten_proxy import ProductsFlattenProxyModel
from .products_grid_widget import (
    DEFAULT_GRID_COLUMNS,
    GRID_COLUMNS_MAX,
    GRID_COLUMNS_MIN,
    ProductsGridWidget,
    columns_from_density_scale,
)
from .products_widget import ProductsWidget
from .repres_widget import RepresentationsWidget
from .scale_slider_overlay import ScaleSliderOverlay
from .search_bar import FilterDefinition, FiltersBar
from .tasks_widget import LoaderTasksWidget
from .view_mode_selector import (
    VIEW_MODE_GRID,
    VIEW_MODE_LIST,
    ViewModeSelector,
)
from .actions_utils import (
    show_loader_drop_action_picker,
    show_loader_drop_rep_action_picker,
)
from ayon_core.tools.loader.drag_drop import (
    decode_loader_drag_payload_from_mime,
    filter_actions_by_drop_context,
    LOADER_PAYLOAD_MIME_TYPE,
)

FIND_KEY_SEQUENCE = QtGui.QKeySequence(
    QtCore.Qt.Modifier.CTRL | QtCore.Qt.Key_F
)
GROUP_KEY_SEQUENCE = QtGui.QKeySequence(
    QtCore.Qt.Modifier.CTRL | QtCore.Qt.Key_G
)

LOADER_SETTINGS_GROUP = "loader"
LOADER_VIEW_MODE_KEY = "view_mode"
LOADER_VIEW_GRID_COLUMNS = "view_grid_columns"
# Legacy float 0.5..2.0; migrated once when LOADER_VIEW_GRID_COLUMNS is absent.
LOADER_VIEW_SCALE_KEY = "view_scale_factor"


class LoadErrorMessageBox(ErrorMessageBox):
    def __init__(self, messages, parent=None):
        self._messages = messages
        super(LoadErrorMessageBox, self).__init__("Loading failed", parent)

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
                'During load error happened on Product: "{product}"'
                ' Representation: "{repre}" Version: {version}'
                "\n\nError message: {message}"
            ).format(
                product=product, repre=repre, version=version, message=exc_msg
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


class LoaderWindow(QtWidgets.QWidget):
    def __init__(self, controller=None, parent=None):
        super(LoaderWindow, self).__init__(parent)

        icon = QtGui.QIcon(get_ayon_icon_filepath())
        self.setWindowIcon(icon)

        # Set window title with application name
        base_title = "AYON Loader"
        app_name = os.environ.get("AYON_APP_NAME") or get_current_host_name()
        if app_name:
            window_title = f"{base_title} - {app_name}"
        else:
            window_title = base_title
        self.setWindowTitle(window_title)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)

        if controller is None:
            controller = LoaderController()

        overlay_object = MessageOverlayObject(self)

        main_splitter = QtWidgets.QSplitter(self)

        context_splitter = QtWidgets.QSplitter(main_splitter)
        context_splitter.setOrientation(QtCore.Qt.Vertical)

        # Context selection widget
        context_widget = QtWidgets.QWidget(context_splitter)

        context_top_widget = QtWidgets.QWidget(context_widget)
        projects_combobox = ProjectsCombobox(
            controller, context_top_widget, handle_expected_selection=True
        )
        projects_combobox.set_select_item_visible(True)
        projects_combobox.set_libraries_separator_visible(True)
        projects_combobox.set_standard_filter_enabled(
            controller.is_standard_projects_filter_enabled()
        )

        go_to_current_btn = GoToCurrentButton(context_top_widget)
        refresh_btn = RefreshButton(context_top_widget)

        context_top_layout = QtWidgets.QHBoxLayout(context_top_widget)
        context_top_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        context_top_layout.addWidget(projects_combobox, 1)
        context_top_layout.addWidget(go_to_current_btn, 0)
        context_top_layout.addWidget(refresh_btn, 0)

        folders_filter_input = PlaceholderLineEdit(context_widget)
        folders_filter_input.setPlaceholderText("Folder name filter...")

        folders_widget = LoaderFoldersWidget(controller, context_widget)

        context_layout = QtWidgets.QVBoxLayout(context_widget)
        context_layout.setContentsMargins(0, 0, 0, 0)
        context_layout.addWidget(context_top_widget, 0)
        context_layout.addWidget(folders_filter_input, 0)
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
        view_mode_selector = ViewModeSelector(products_inputs_widget)

        product_group_checkbox = QtWidgets.QCheckBox(
            "Enable grouping", products_inputs_widget
        )
        product_group_checkbox.setChecked(True)

        products_inputs_layout = QtWidgets.QHBoxLayout(products_inputs_widget)
        products_inputs_layout.setContentsMargins(0, 0, 0, 0)
        products_inputs_layout.addWidget(search_bar, 1)
        products_inputs_layout.addWidget(view_mode_selector, 0)
        products_inputs_layout.addWidget(product_group_checkbox, 0)

        products_stack = QtWidgets.QStackedWidget(products_wrap_widget)
        products_stack.setObjectName("LoaderProductsStack")
        products_widget = ProductsWidget(controller, products_stack)
        flatten_proxy = ProductsFlattenProxyModel(products_stack)
        flatten_proxy.setSourceModel(products_widget.get_proxy_model())
        products_grid_widget = ProductsGridWidget(
            controller, flatten_proxy, products_stack
        )
        products_stack.addWidget(products_widget)
        products_stack.addWidget(products_grid_widget)

        products_container = QtWidgets.QWidget(products_wrap_widget)
        products_container_layout = QtWidgets.QGridLayout(products_container)
        products_container_layout.setContentsMargins(0, 0, 0, 0)
        products_container_layout.addWidget(products_stack, 0, 0)
        scale_slider_overlay = ScaleSliderOverlay(products_container)
        products_container_layout.addWidget(
            scale_slider_overlay,
            0,
            0,
            QtCore.Qt.AlignmentFlag.AlignRight
            | QtCore.Qt.AlignmentFlag.AlignBottom,
        )
        scale_slider_overlay.hide()

        products_wrap_layout = QtWidgets.QVBoxLayout(products_wrap_widget)
        products_wrap_layout.setContentsMargins(0, 0, 0, 0)
        products_wrap_layout.addWidget(products_inputs_widget, 0)
        products_wrap_layout.addWidget(products_container, 1)

        right_panel_splitter = QtWidgets.QSplitter(main_splitter)
        right_panel_splitter.setOrientation(QtCore.Qt.Vertical)

        thumbnails_widget = ThumbnailPainterWidget(right_panel_splitter)
        thumbnails_widget.set_use_checkboard(False)
        # Connect double-click signal to open thumbnail
        thumbnails_widget.thumbnail_double_clicked.connect(
            self._on_thumbnail_double_clicked
        )

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

        show_timer = QtCore.QTimer()
        show_timer.setInterval(1)

        show_timer.timeout.connect(self._on_show_timer)

        projects_combobox.refreshed.connect(self._on_projects_refresh)
        folders_widget.refreshed.connect(self._on_folders_refresh)
        products_widget.refreshed.connect(self._on_products_refresh)
        folders_filter_input.textChanged.connect(self._on_folder_filter_change)
        search_bar.filter_changed.connect(self._on_filter_change)
        product_group_checkbox.stateChanged.connect(
            self._on_product_group_change
        )
        view_mode_selector.view_mode_changed.connect(
            self._on_view_mode_changed
        )
        scale_slider_overlay.grid_columns_changed.connect(
            self._on_grid_columns_changed
        )
        products_grid_widget.column_bounds_changed.connect(
            self._on_grid_column_bounds_changed
        )
        products_grid_widget.grid_columns_clamped.connect(
            self._on_grid_columns_clamped
        )
        products_grid_widget.scale_change_requested.connect(
            self._on_scale_change_requested
        )
        products_widget.merged_products_selection_changed.connect(
            self._on_merged_products_selection_change
        )
        products_widget.selection_changed.connect(
            self._on_products_selection_change
        )
        products_grid_widget.merged_products_selection_changed.connect(
            self._on_merged_products_selection_change
        )
        products_grid_widget.selection_changed.connect(
            self._on_products_selection_change
        )
        go_to_current_btn.clicked.connect(self._on_go_to_current_context_click)
        refresh_btn.clicked.connect(self._on_refresh_click)
        controller.register_event_callback(
            "load.started",
            self._on_load_started,
        )
        controller.register_event_callback(
            "load.progress",
            self._on_load_progress,
        )
        controller.register_event_callback(
            "load.finished",
            self._on_load_finished,
        )
        controller.register_event_callback(
            "loader.action.finished",
            self._on_loader_action_finished,
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

        self._group_dialog = ProductGroupDialog(controller, self)

        self._main_splitter = main_splitter

        self._go_to_current_btn = go_to_current_btn
        self._refresh_btn = refresh_btn
        self._projects_combobox = projects_combobox

        self._folders_filter_input = folders_filter_input
        self._folders_widget = folders_widget

        self._tasks_widget = tasks_widget

        self._search_bar = search_bar
        self._product_group_checkbox = product_group_checkbox
        self._view_mode_selector = view_mode_selector
        self._products_stack = products_stack
        self._products_widget = products_widget
        self._products_grid_widget = products_grid_widget
        self._flatten_proxy = flatten_proxy
        self._scale_slider_overlay = scale_slider_overlay
        self._view_grid_columns = DEFAULT_GRID_COLUMNS

        self._grid_activate_timer = QtCore.QTimer(self)
        self._grid_activate_timer.setSingleShot(True)
        self._grid_activate_timer.timeout.connect(
            self._apply_grid_view_after_show
        )

        self._right_panel_splitter = right_panel_splitter
        self._thumbnails_widget = thumbnails_widget
        self._info_widget = info_widget
        self._repre_widget = repre_widget

        self._controller = controller
        self._overlay_object = overlay_object
        self._refresh_handler = RefreshHandler()
        self.setAcceptDrops(True)
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
        self._load_view_settings()
        self._products_grid_widget.set_grid_columns(self._view_grid_columns)

    def _load_view_settings(self):
        settings = QtCore.QSettings()
        settings.beginGroup(LOADER_SETTINGS_GROUP)
        mode = settings.value(LOADER_VIEW_MODE_KEY, VIEW_MODE_LIST, type=str)
        if settings.contains(LOADER_VIEW_GRID_COLUMNS):
            try:
                cols = int(settings.value(LOADER_VIEW_GRID_COLUMNS))
            except (TypeError, ValueError):
                cols = DEFAULT_GRID_COLUMNS
        elif settings.contains(LOADER_VIEW_SCALE_KEY):
            try:
                cols = columns_from_density_scale(
                    float(settings.value(LOADER_VIEW_SCALE_KEY))
                )
            except (TypeError, ValueError):
                cols = DEFAULT_GRID_COLUMNS
        else:
            cols = DEFAULT_GRID_COLUMNS
        cols = max(GRID_COLUMNS_MIN, min(GRID_COLUMNS_MAX, int(cols)))
        settings.endGroup()
        self._view_grid_columns = cols
        self._scale_slider_overlay.set_grid_columns(cols)
        if mode in (VIEW_MODE_LIST, VIEW_MODE_GRID):
            self._view_mode_selector.sync_from_stack_index(
                1 if mode == VIEW_MODE_GRID else 0
            )
            self._on_view_mode_changed(mode)
        else:
            self._view_mode_selector.sync_from_stack_index(0)
            self._on_view_mode_changed(VIEW_MODE_LIST)

    def _save_view_settings(self):
        settings = QtCore.QSettings()
        settings.beginGroup(LOADER_SETTINGS_GROUP)
        settings.setValue(
            LOADER_VIEW_MODE_KEY,
            self._view_mode_selector.get_view_mode(),
        )
        settings.setValue(
            LOADER_VIEW_GRID_COLUMNS,
            self._products_grid_widget.get_grid_columns(),
        )
        settings.endGroup()

    def _get_current_products_view(self):
        return self._products_stack.currentWidget()

    def _on_view_mode_changed(self, mode_id: str):
        if mode_id == VIEW_MODE_LIST:
            self._grid_activate_timer.stop()
            self._products_stack.setCurrentIndex(0)
            self._scale_slider_overlay.hide()
            self._products_grid_widget.set_overlay_bottom_height(0)
        elif mode_id == VIEW_MODE_GRID:
            self._products_stack.setCurrentIndex(1)
            self._scale_slider_overlay.show()
            overlay_h = self._scale_slider_overlay.sizeHint().height()
            self._products_grid_widget.set_overlay_bottom_height(overlay_h)
            self._grid_activate_timer.stop()
            self._grid_activate_timer.start(10)
        self._view_mode_selector.sync_from_stack_index(
            self._products_stack.currentIndex()
        )
        self._save_view_settings()

    def _on_grid_column_bounds_changed(self, lo: int, hi: int) -> None:
        self._scale_slider_overlay.set_column_bounds(lo, hi)

    def _on_grid_columns_clamped(self, n: int) -> None:
        n = int(n)
        prev = int(self._view_grid_columns)
        self._view_grid_columns = n
        self._scale_slider_overlay.set_grid_columns(n)
        if n != prev:
            self._save_view_settings()

    def _apply_grid_view_after_show(self):
        mode = self._view_mode_selector.get_view_mode()
        if mode != VIEW_MODE_GRID:
            return
        lo, hi = self._products_grid_widget.compute_column_bounds()
        self._scale_slider_overlay.set_column_bounds(lo, hi)
        self._view_grid_columns = max(
            lo, min(hi, int(self._view_grid_columns))
        )
        self._products_grid_widget.set_grid_columns(self._view_grid_columns)
        self._scale_slider_overlay.set_grid_columns(self._view_grid_columns)
        version_ids = self._controller.get_selected_version_ids()
        if version_ids:
            self._products_grid_widget.set_selection_from_version_ids(
                set(version_ids)
            )

    def _on_grid_columns_changed(self, cols: int):
        lo, hi = self._products_grid_widget.get_column_bounds()
        cols = max(lo, min(hi, int(cols)))
        self._view_grid_columns = cols
        self._products_grid_widget.set_grid_columns(cols)
        self._save_view_settings()

    def _on_scale_change_requested(self, delta: int):
        cols = self._products_grid_widget.get_grid_columns()
        lo, hi = self._products_grid_widget.get_column_bounds()
        cols = max(lo, min(hi, cols - delta))
        self._view_grid_columns = cols
        self._scale_slider_overlay.set_grid_columns(cols)
        self._products_grid_widget.set_grid_columns(cols)
        self._save_view_settings()

        try:
            from ayon_core.tools.tray.tool_window_identity_apply import (
                apply_loader_window_identity,
            )

            apply_loader_window_identity(self)
        except ImportError:
            pass

        try:
            from ayon_core.tools.tray.tool_window_identity_apply import (
                apply_loader_window_identity,
            )

            apply_loader_window_identity(self)
        except ImportError:
            pass

    def refresh(self):
        self._reset_on_show = False
        self._controller.reset()

    def showEvent(self, event):
        super().showEvent(event)

        if self._first_show:
            self._on_first_show()

        self._show_timer.start()

    def closeEvent(self, event):
        save_tool_window_state(
            "loader",
            self,
            [
                ("main_splitter", self._main_splitter),
                ("right_panel_splitter", self._right_panel_splitter),
            ],
        )
        super().closeEvent(event)

        self._reset_on_show = True

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(LOADER_PAYLOAD_MIME_TYPE):
            event.acceptProposedAction()

    def dropEvent(self, event):
        mime_data = event.mimeData()
        if not mime_data.hasFormat(LOADER_PAYLOAD_MIME_TYPE):
            return
        payload = decode_loader_drag_payload_from_mime(mime_data)
        if not payload:
            return
        event.acceptProposedAction()
        project_name = payload["project_name"]
        entity_type = payload["entity_type"]
        entity_ids = set(payload.get("entity_ids") or [])

        def trigger(identifier, data, options, form_values):
            d = dict(data or {})
            ids_from_data = d.get("entity_ids")
            if ids_from_data:
                sel_ids = set(ids_from_data)
                etype = "representation"
            else:
                sel_ids = entity_ids
                etype = entity_type
            self._controller.trigger_action_item(
                identifier=identifier,
                project_name=project_name,
                selected_ids=sel_ids,
                selected_entity_type=etype,
                data=d,
                options=options or {},
                form_values=form_values or {},
            )

        if payload.get("needs_rep_choice"):
            show_loader_drop_rep_action_picker(
                payload.get("repre_names_by_id") or {},
                payload.get("actions_by_repre_id") or {},
                trigger,
                self,
            )
            return

        actions = filter_actions_by_drop_context(payload, None)
        if not actions:
            items = self._controller.get_drag_drop_action_items(
                project_name, entity_ids, entity_type
            )
            actions = [
                {
                    "identifier": i.identifier,
                    "data": i.data,
                    "label": i.label,
                    "default_for_drag_drop": getattr(
                        i, "default_for_drag_drop", False
                    ),
                    "drag_drop_contexts": (
                        list(i.drag_drop_contexts)
                        if getattr(i, "drag_drop_contexts", None)
                        else None
                    ),
                }
                for i in (items or [])
            ]

        if not actions:
            return

        defaults = [a for a in actions if a.get("default_for_drag_drop")]
        if len(actions) == 1:
            a = actions[0]
            trigger(a.get("identifier", ""), a.get("data"), {}, {})
            return
        if len(defaults) == 1:
            a = defaults[0]
            trigger(a.get("identifier", ""), a.get("data"), {}, {})
            return
        show_loader_drop_action_picker(actions, trigger, self)

    def keyPressEvent(self, event):
        if hasattr(event, "keyCombination"):
            combination = event.keyCombination()
        else:
            combination = QtGui.QKeySequence(event.modifiers() | event.key())
        if FIND_KEY_SEQUENCE == combination and not event.isAutoRepeat():
            self._search_bar.show_filters_popup()
            event.setAccepted(True)
            return

        # Grouping products on pressing Ctrl + G
        if GROUP_KEY_SEQUENCE == combination and not event.isAutoRepeat():
            self._show_group_dialog()
            event.setAccepted(True)
            return

        super().keyPressEvent(event)

    def _on_first_show(self):
        self._first_show = False
        self.setStyleSheet(load_stylesheet())
        if not restore_tool_window_state(
            "loader",
            self,
            [
                ("main_splitter", self._main_splitter),
                ("right_panel_splitter", self._right_panel_splitter),
            ],
        ):
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
            center_window(self)

    def _on_show_timer(self):
        if self._show_counter < 2:
            self._show_counter += 1
            return

        self._show_counter = 0
        self._show_timer.stop()

        if self._reset_on_show:
            self.refresh()

    def _show_group_dialog(self):
        project_name = self._projects_combobox.get_selected_project_name()
        if not project_name:
            return

        product_ids = {
            version_info["product_id"]
            for version_info in (
                self._get_current_products_view().get_selected_version_info()
            )
        }
        if not product_ids:
            return

        self._group_dialog.set_product_ids(
            project_name,
            set(self._selected_folder_ids),
            product_ids,
        )
        self._group_dialog.show()

    def _on_folder_filter_change(self, text):
        self._folders_widget.set_name_filter(text)

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
            self._products_grid_widget.set_statuses_filter(status_names)

        elif filter_name == "version_tags":
            version_tags = self._search_bar.get_filter_value("version_tags")
            self._products_widget.set_version_tags_filter(version_tags)
            self._products_grid_widget.set_version_tags_filter(version_tags)

        elif filter_name == "task_tags":
            task_tags = self._search_bar.get_filter_value("task_tags")
            self._products_widget.set_task_tags_filter(task_tags)
            self._products_grid_widget.set_task_tags_filter(task_tags)

    def _on_tasks_selection_change(self, event):
        self._products_widget.set_tasks_filter(event["task_ids"])
        self._products_grid_widget.set_tasks_filter(event["task_ids"])

    def _on_merged_products_selection_change(self):
        items = (
            self._get_current_products_view().get_selected_merged_products()
        )
        self._folders_widget.set_merged_products_selection(items)

    def _on_products_selection_change(self):
        items = self._get_current_products_view().get_selected_version_info()
        self._info_widget.set_selected_version_info(
            self._projects_combobox.get_selected_project_name(), items
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

    def _on_load_started(self, event):
        """Handle load.started event and show toast notification."""
        message = event.get("message")
        message_id = event["id"]

        if message:
            self._overlay_object.add_message(message, message_id=message_id)
        else:
            # Fallback message if loader doesn't provide one
            self._overlay_object.add_message(
                "Loading...", message_id=message_id
            )

        # Show progress bar for this message
        self._overlay_object.set_progress_visible(message_id, True)

    def _on_load_progress(self, event):
        """Handle load.progress event to update progress bar."""
        message_id = event.get("id")
        progress = event.get("progress", 0)
        current = event.get("current", 0)
        total = event.get("total", 0)
        message = event.get("message")

        if message_id:
            # Prefer plugin message; otherwise show current/total
            if message:
                display_message = f"{message} ({progress}%)"
            elif total > 0:
                display_message = f"Loading {current}/{total}... ({progress}%)"
            else:
                display_message = f"Progress: {progress}%"
            self._overlay_object.update_progress(
                message_id, progress, display_message
            )

    def _on_load_finished(self, event):
        message_id = event["id"]
        # Hide the progress bar when finished
        self._overlay_object.set_progress_visible(message_id, False)

        error_info = event["error_info"]
        if not error_info:
            # Show completion message if load was successful
            self._overlay_object.add_message(
                "Loading completed successfully",
                message_id=message_id,
                message_type="success",
            )
            return

        box = LoadErrorMessageBox(error_info, self)
        box.show()

    def _on_loader_action_finished(self, event):
        message_id = event["id"]
        crashed = event["crashed"]
        if crashed:
            self._overlay_object.add_message(
                "Action failed",
                message_id=message_id,
                message_type="error",
            )
            return

        result: Optional[LoaderActionResult] = event["result"]
        if result is None:
            return

        if result.message:
            message_type = "success" if result.success else "error"
            self._overlay_object.add_message(
                result.message,
                message_id=message_id,
                message_type=message_type,
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

        if not dialog.exec_():
            return

        self._controller.trigger_action_item(
            identifier=event["identifier"],
            project_name=event["project_name"],
            selected_ids=set(event["selected_ids"]),
            selected_entity_type=event["selected_entity_type"],
            data=event["data"],
            options={},
            form_values=dialog.get_values(),
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
            tag_item.name: tag_item.color for tag_item in tag_items
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
                "icon": {
                    "type": "material-symbols",
                    "name": status_item.icon,
                    "color": status_item.color,
                },
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

        self._search_bar.set_search_items(
            [
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
            ]
        )

        # Set product types filter from settings
        if self._set_product_type_filters:
            self._set_product_type_filters = False
            product_types_filter = self._controller.get_product_types_filter()
            product_types = []
            for item in filter_product_type_items:
                product_type = item["value"]
                matching = int(
                    product_type in product_types_filter.product_types
                ) + int(product_types_filter.is_allow_list)
                if matching % 2 == 0:
                    product_types.append(product_type)

            if product_types and len(product_types) < len(
                filter_product_type_items
            ):
                self._search_bar.set_filter_value(
                    "product_types", product_types
                )

    def _on_folders_selection_changed(self, event):
        self._selected_folder_ids = set(event["folder_ids"])
        self._update_thumbnails()

    def _on_versions_selection_changed(self, event):
        self._selected_version_ids = set(event["version_ids"])
        self._update_thumbnails()

    def _get_video_representation_path(self, project_name, version_ids):
        """Get h264_* video representation path for versions.

        Returns path to h264_* representation if available, otherwise None.

        Args:
            project_name (str): Project name.
            version_ids (set[str]): Version ids.

        Returns:
            Union[str, None]: Path to video representation or None.
        """
        if not version_ids or not project_name:
            return None

        try:
            import ayon_api
            from ayon_core.pipeline import Anatomy
            from ayon_core.pipeline.load import (
                get_representation_path_with_anatomy,
            )

            # Get representations for versions
            repre_items = self._controller.get_representation_items(
                project_name, version_ids
            )

            # Look for h264_* representations first (prioritize them)
            h264_repres = []
            other_video_repres = []

            for repre_item in repre_items:
                repre_name = repre_item.representation_name.lower()
                if "h264" in repre_name:
                    h264_repres.append(repre_item)
                elif any(
                    ext in repre_name
                    for ext in ["mp4", "mov", "avi", "mkv", "webm"]
                ):
                    other_video_repres.append(repre_item)

            # Prioritize h264_* representations
            target_repres = h264_repres if h264_repres else other_video_repres

            for repre_item in target_repres:
                representation_id = repre_item.representation_id
                try:
                    repre_entity = ayon_api.get_representation_by_id(
                        project_name, representation_id
                    )
                    if repre_entity:
                        anatomy = Anatomy(project_name)
                        video_path = get_representation_path_with_anatomy(
                            repre_entity, anatomy
                        )
                        if video_path:
                            if hasattr(video_path, "normalized"):
                                video_path_str = str(video_path.normalized())
                            else:
                                video_path_str = str(video_path)
                            if os.path.exists(video_path_str):
                                return video_path_str
                except Exception as e:
                    print(
                        f"Failed to get representation path "
                        f"for {representation_id}: {e}"
                    )
                    continue

        except Exception as e:
            print(f"Failed to get h264 representation path: {e}")

        return None

    def _update_thumbnails(self):
        # TODO make this threaded and show loading animation while running
        project_name = self._selected_project_name
        entity_type = None
        entity_ids = set()

        # First check for video representations in selected versions
        video_path = None
        if self._selected_version_ids:
            entity_ids = set(self._selected_version_ids)
            entity_type = "version"

            # Try to get h264_* video representation
            video_path = self._get_video_representation_path(
                project_name, entity_ids
            )

        elif self._selected_folder_ids:
            entity_ids = set(self._selected_folder_ids)
            entity_type = "folder"

        # If we have a video path, use it directly
        if video_path:
            self._thumbnails_widget.set_current_thumbnail_paths([video_path])
            return

        # Otherwise use standard thumbnail system
        thumbnail_path_by_entity_id = self._controller.get_thumbnail_paths(
            project_name, entity_type, entity_ids
        )
        thumbnail_paths = set(thumbnail_path_by_entity_id.values())
        thumbnail_paths.discard(None)

        if thumbnail_paths:
            self._thumbnails_widget.set_current_thumbnail_paths(
                list(thumbnail_paths)
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

    def _on_thumbnail_double_clicked(self, thumbnail_path):
        """Handle thumbnail double-click to open image with system default."""
        import os
        import subprocess
        import sys

        try:
            if sys.platform.startswith("darwin"):
                subprocess.call(("open", thumbnail_path))
            elif os.name == "nt":
                os.startfile(thumbnail_path)
            elif os.name == "posix":
                subprocess.call(("xdg-open", thumbnail_path))
        except Exception as e:
            print(f"Failed to open thumbnail {thumbnail_path}: {e}")
