from qtpy import QtWidgets, QtCore, QtGui

from ayon_core.resources import get_ayon_icon_filepath
from ayon_core.style import load_stylesheet
from ayon_core.tools.utils import (
    PlaceholderLineEdit,
    ErrorMessageBox,
    ThumbnailPainterWidget,
    RefreshButton,
    GoToCurrentButton,
)
from ayon_core.tools.utils.lib import center_window
from ayon_core.tools.utils import ProjectsCombobox
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


class LoaderWindow(QtWidgets.QWidget):
    def __init__(self, controller=None, parent=None):
        super(LoaderWindow, self).__init__(parent)

        icon = QtGui.QIcon(get_ayon_icon_filepath())
        self.setWindowIcon(icon)
        self.setWindowTitle("AYON Loader")
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)

        if controller is None:
            controller = LoaderController()

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

        show_timer = QtCore.QTimer()
        show_timer.setInterval(1)

        show_timer.timeout.connect(self._on_show_timer)

        projects_combobox.refreshed.connect(self._on_projects_refresh)
        folders_widget.refreshed.connect(self._on_folders_refresh)
        products_widget.refreshed.connect(self._on_products_refresh)
        folders_filter_input.textChanged.connect(
            self._on_folder_filter_change
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

        self._products_widget.set_enable_grouping(
            self._product_group_checkbox.isChecked()
        )

    def refresh(self):
        self._reset_on_show = False
        self._controller.reset()

    def showEvent(self, event):
        super().showEvent(event)

        if self._first_show:
            self._on_first_show()

        self._show_timer.start()

    def closeEvent(self, event):
        super().closeEvent(event)

        self._reset_on_show = True

    def keyPressEvent(self, event):
        modifiers = event.modifiers()
        ctrl_pressed = QtCore.Qt.ControlModifier & modifiers

        # Grouping products on pressing Ctrl + G
        if (
            ctrl_pressed
            and event.key() == QtCore.Qt.Key_G
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

    def _show_group_dialog(self):
        project_name = self._projects_combobox.get_selected_project_name()
        if not project_name:
            return

        product_ids = {
            i["product_id"]
            for i in self._products_widget.get_selected_version_info()
        }
        if not product_ids:
            return

        self._group_dialog.set_product_ids(project_name, product_ids)
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

    def _on_load_finished(self, event):
        error_info = event["error_info"]
        if not error_info:
            return

        box = LoadErrorMessageBox(error_info, self)
        box.show()

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
                "icon": {
                    "type": "material-symbols",
                    "name": status_item.icon,
                    "color": status_item.color
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
