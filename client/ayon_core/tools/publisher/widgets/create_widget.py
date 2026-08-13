from __future__ import annotations

import re
import collections
import typing

from qtpy import QtWidgets, QtCore, QtGui

from ayon_core.lib import MaterialSymbolsIcon
from ayon_core.pipeline.create import (
    PRODUCT_NAME_ALLOWED_SYMBOLS,
    PRE_CREATE_THUMBNAIL_KEY,
    DEFAULT_VARIANT_VALUE,
    TaskNotSetError,
)

from ayon_core.tools.publisher.abstract import SubtaskProduct
from ayon_core.tools.publisher.constants import (
    VARIANT_TOOLTIP,
    CREATOR_IDENTIFIER_ROLE,
    PRODUCT_TYPE_ROLE,
    PRODUCT_BASE_TYPE_ROLE,
    CREATOR_THUMBNAIL_ENABLED_ROLE,
    CREATOR_SORT_ROLE,
    INPUTS_LAYOUT_HSPACING,
    INPUTS_LAYOUT_VSPACING,
)
from ayon_core.tools.utils import HintedLineEdit, ListView, get_qt_icon

from .thumbnail_widget import ThumbnailWidget
from .widgets import (
    IconValuePixmapLabel,
    CreateBtn,
)
from .create_context_widgets import CreateContextWidget
from .precreate_widget import PreCreateWidget

if typing.TYPE_CHECKING:
    from ayon_core.tools.publisher.abstract import (
        CreatorItem,
        AbstractPublisherFrontend,
    )

SUBTASK_PRODUCT_NAME_ROLE = QtCore.Qt.UserRole + 1
SUBTASK_PRODUCT_BASE_TYPE_ROLE = QtCore.Qt.UserRole + 2
SUBTASK_PRODUCT_TYPE_ROLE = QtCore.Qt.UserRole + 3
SUBTASK_PRODUCT_CREATED_ROLE = QtCore.Qt.UserRole + 4
SUBTASK_PRODUCT_SORT_ROLE = QtCore.Qt.UserRole + 5


class ResizeControlWidget(QtWidgets.QWidget):
    resized = QtCore.Signal()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resized.emit()


# TODO add creator identifier/label to details
class CreatorShortDescWidget(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent=parent)

        # --- Short description widget ---
        icon_widget = IconValuePixmapLabel(None, self)
        icon_widget.setObjectName("ProductTypeIconLabel")

        # --- Short description inputs ---
        short_desc_input_widget = QtWidgets.QWidget(self)

        product_base_type_label = QtWidgets.QLabel(short_desc_input_widget)
        product_base_type_label.setAlignment(
            QtCore.Qt.AlignBottom | QtCore.Qt.AlignLeft
        )

        description_label = QtWidgets.QLabel(short_desc_input_widget)
        description_label.setAlignment(
            QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft
        )

        short_desc_input_layout = QtWidgets.QVBoxLayout(
            short_desc_input_widget
        )
        short_desc_input_layout.setSpacing(0)
        short_desc_input_layout.addWidget(product_base_type_label)
        short_desc_input_layout.addWidget(description_label)
        # --------------------------------

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(icon_widget, 0)
        layout.addWidget(short_desc_input_widget, 1)
        # --------------------------------

        self._icon_widget = icon_widget
        self._product_base_type_label = product_base_type_label
        self._description_label = description_label

    def set_creator_item(
        self,
        creator_item: CreatorItem | None = None,
        product_type: str | None = None,
    ) -> None:
        if not creator_item:
            self._icon_widget.set_icon_def(None)
            self._product_base_type_label.setText("")
            self._description_label.setText("")
            return

        plugin_icon = creator_item.icon
        description = creator_item.description or ""
        product_base_type = creator_item.product_base_type
        product_base_label = ""
        if product_base_type != product_type:
            product_base_label = f" [<i>{product_base_type}</i>]"
        self._icon_widget.set_icon_def(plugin_icon)
        self._product_base_type_label.setText(
            f"<b>{product_type}{product_base_label}</b>"
        )
        self._product_base_type_label.setTextInteractionFlags(
            QtCore.Qt.NoTextInteraction
        )
        self._description_label.setText(description)


class CreatorsProxyModel(QtCore.QSortFilterProxyModel):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._subset_product: SubtaskProduct | None = None

    def set_subset_product_filter(
        self, subset_product: SubtaskProduct | None
    ) -> None:
        if subset_product is self._subset_product:
            return
        self._subset_product = subset_product
        if self.rowCount() == 0:
            return

        first = self.index(0, 0)
        last = self.index(self.rowCount() - 1, 0)
        # UserRole - 1 is role under which are stored flags
        self.dataChanged.emit(first, last, [QtCore.Qt.UserRole - 1])

    def flags(self, source_index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlags:
        flags = super().flags(source_index)
        if not source_index.isValid():
            return flags

        if self._subset_product is None:
            return flags

        product_base_type = source_index.data(PRODUCT_BASE_TYPE_ROLE)
        if product_base_type != self._subset_product.product_base_type:
            return flags & ~QtCore.Qt.ItemIsEnabled

        return flags

    def lessThan(self, left, right):
        l_show_order = left.data(CREATOR_SORT_ROLE)
        r_show_order = right.data(CREATOR_SORT_ROLE)
        if l_show_order == r_show_order:
            return super().lessThan(left, right)
        return l_show_order < r_show_order


class SubtaskProductsView(ListView):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.set_deselectable(True)

    def sizeHint(self):
        hint = super().sizeHint()
        row_height = self.sizeHintForRow(0)
        if row_height <= 0:
            row_height = 20
        height = row_height * 6 + self.frameWidth() * 2
        hint.setHeight(height)
        return hint


class CreateWidget(QtWidgets.QWidget):
    def __init__(
        self,
        controller: AbstractPublisherFrontend,
        parent: QtWidgets.QWidget,
    ) -> None:
        super().__init__(parent)

        self._controller: AbstractPublisherFrontend = controller

        self._folder_path = None
        self._product_names = None
        self._selected_creator_identifier = None
        self._selected_product_type = None

        self._prereq_available = False

        name_pattern = f"^[{PRODUCT_NAME_ALLOWED_SYMBOLS}]*$"
        self._name_pattern = name_pattern
        self._compiled_name_pattern = re.compile(name_pattern)

        main_splitter_widget = QtWidgets.QSplitter(self)

        context_widget = CreateContextWidget(controller, main_splitter_widget)

        # --- Creators view ---
        creators_widget = QtWidgets.QWidget(main_splitter_widget)

        creator_short_desc_widget = CreatorShortDescWidget(creators_widget)

        attr_separator_widget = QtWidgets.QWidget(creators_widget)
        attr_separator_widget.setObjectName("Separator")
        attr_separator_widget.setMinimumHeight(1)
        attr_separator_widget.setMaximumHeight(1)

        creators_splitter = QtWidgets.QSplitter(creators_widget)

        creators_view_widget = QtWidgets.QWidget(creators_splitter)

        subtask_products_widget = QtWidgets.QWidget(creators_view_widget)
        subtask_products_widget.setVisible(False)

        subtask_products_label = QtWidgets.QLabel(
            "Expected products", subtask_products_widget
        )

        subtask_products_view = SubtaskProductsView(subtask_products_widget)
        subtask_products_model = QtGui.QStandardItemModel()
        subtask_products_proxy_model = QtCore.QSortFilterProxyModel(
            subtask_products_view
        )
        subtask_products_proxy_model.setSourceModel(subtask_products_model)
        subtask_products_proxy_model.setSortRole(SUBTASK_PRODUCT_SORT_ROLE)
        subtask_products_proxy_model.setDynamicSortFilter(True)
        subtask_products_view.setModel(subtask_products_proxy_model)

        subtask_products_layout = QtWidgets.QVBoxLayout(
            subtask_products_widget
        )
        subtask_products_layout.setContentsMargins(0, 0, 0, 0)
        subtask_products_layout.addWidget(subtask_products_label, 0)
        subtask_products_layout.addWidget(subtask_products_view, 1)

        creator_view_label = QtWidgets.QLabel(
            "Choose publish type", creators_view_widget
        )

        creators_view = QtWidgets.QListView(creators_view_widget)
        creators_model = QtGui.QStandardItemModel()
        creators_sort_model = CreatorsProxyModel()
        creators_sort_model.setSourceModel(creators_model)
        creators_view.setModel(creators_sort_model)

        creators_view_layout = QtWidgets.QVBoxLayout(creators_view_widget)
        creators_view_layout.setContentsMargins(0, 0, 0, 0)
        creators_view_layout.addWidget(subtask_products_widget, 0)
        creators_view_layout.addWidget(creator_view_label, 0)
        creators_view_layout.addWidget(creators_view, 1)

        # --- Creator attr defs ---
        creators_attrs_widget = QtWidgets.QWidget(creators_splitter)

        # Top part - variant / product name + thumbnail
        creators_attrs_top = QtWidgets.QWidget(creators_attrs_widget)

        # Basics - variant / product name
        creator_basics_widget = ResizeControlWidget(creators_attrs_top)

        product_variant_label = QtWidgets.QLabel(
            "Create options", creator_basics_widget
        )

        product_variant_widget = QtWidgets.QWidget(creator_basics_widget)
        # Variant and product input
        variant_widget = HintedLineEdit(parent=product_variant_widget)
        variant_widget.set_text_widget_object_name("VariantInput")
        variant_widget.setToolTip(VARIANT_TOOLTIP)

        product_name_input = QtWidgets.QLineEdit(product_variant_widget)
        product_name_input.setEnabled(False)

        product_variant_layout = QtWidgets.QFormLayout(product_variant_widget)
        product_variant_layout.setContentsMargins(0, 0, 0, 0)
        product_variant_layout.setHorizontalSpacing(INPUTS_LAYOUT_HSPACING)
        product_variant_layout.setVerticalSpacing(INPUTS_LAYOUT_VSPACING)
        product_variant_layout.addRow("Variant", variant_widget)
        product_variant_layout.addRow("Product", product_name_input)

        creator_basics_layout = QtWidgets.QVBoxLayout(creator_basics_widget)
        creator_basics_layout.setContentsMargins(0, 0, 0, 0)
        creator_basics_layout.addWidget(product_variant_label, 0)
        creator_basics_layout.addWidget(product_variant_widget, 0)

        thumbnail_widget = ThumbnailWidget(controller, creators_attrs_top)

        creators_attrs_top_layout = QtWidgets.QHBoxLayout(creators_attrs_top)
        creators_attrs_top_layout.setContentsMargins(0, 0, 0, 0)
        creators_attrs_top_layout.addWidget(creator_basics_widget, 1)
        creators_attrs_top_layout.addWidget(thumbnail_widget, 0)

        # Precreate attributes widget
        pre_create_widget = PreCreateWidget(controller, creators_attrs_widget)

        # Create button
        create_btn_wrapper = QtWidgets.QWidget(creators_attrs_widget)
        create_btn = CreateBtn(create_btn_wrapper)
        create_btn.setEnabled(False)

        create_btn_wrap_layout = QtWidgets.QHBoxLayout(create_btn_wrapper)
        create_btn_wrap_layout.setContentsMargins(0, 0, 0, 0)
        create_btn_wrap_layout.addStretch(1)
        create_btn_wrap_layout.addWidget(create_btn, 0)

        creators_attrs_layout = QtWidgets.QVBoxLayout(creators_attrs_widget)
        creators_attrs_layout.setContentsMargins(0, 0, 0, 0)
        creators_attrs_layout.addWidget(creators_attrs_top, 0)
        creators_attrs_layout.addWidget(pre_create_widget, 1)
        creators_attrs_layout.addWidget(create_btn_wrapper, 0)

        creators_splitter.addWidget(creators_view_widget)
        creators_splitter.addWidget(creators_attrs_widget)
        creators_splitter.setStretchFactor(0, 1)
        creators_splitter.setStretchFactor(1, 2)

        creators_layout = QtWidgets.QVBoxLayout(creators_widget)
        creators_layout.setContentsMargins(0, 0, 0, 0)
        creators_layout.addWidget(creator_short_desc_widget, 0)
        creators_layout.addWidget(attr_separator_widget, 0)
        creators_layout.addWidget(creators_splitter, 1)
        # ------------

        # --- Detailed information about creator ---
        # Detailed description of creator
        # TODO this has no way how can be showed now

        # -------------------------------------------
        main_splitter_widget.addWidget(context_widget)
        main_splitter_widget.addWidget(creators_widget)
        main_splitter_widget.setStretchFactor(0, 1)
        main_splitter_widget.setStretchFactor(1, 3)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(main_splitter_widget, 1)

        prereq_timer = QtCore.QTimer()
        prereq_timer.setInterval(50)
        prereq_timer.setSingleShot(True)

        prereq_timer.timeout.connect(self._invalidate_prereq)

        create_btn.clicked.connect(self._on_create)
        creator_basics_widget.resized.connect(self._on_creator_basics_resize)
        variant_widget.returnPressed.connect(self._on_create)
        variant_widget.textChanged.connect(self._on_variant_change)
        subtask_products_view.selectionModel().currentChanged.connect(
            self._on_subtask_product_change
        )
        creators_view.selectionModel().currentChanged.connect(
            self._on_creator_item_change
        )
        context_widget.folder_changed.connect(self._on_folder_change)
        context_widget.task_changed.connect(self._on_task_change)
        thumbnail_widget.thumbnail_created.connect(self._on_thumbnail_create)
        thumbnail_widget.thumbnail_cleared.connect(self._on_thumbnail_clear)

        controller.register_event_callback(
            "main.window.closed", self._on_main_window_close
        )
        controller.register_event_callback(
            "controller.reset.finished", self._on_controler_reset
        )
        controller.register_event_callback(
            "create.context.pre.create.attrs.changed",
            self._pre_create_attr_changed
        )
        controller.register_event_callback(
            "create.context.removed.instance",
            self._on_instances_removed
        )

        self._main_splitter_widget = main_splitter_widget

        self._creators_splitter = creators_splitter

        self._context_widget = context_widget

        self.product_name_input = product_name_input

        self._variant_widget = variant_widget

        self._subtask_products_widget = subtask_products_widget
        self._subtask_products_view = subtask_products_view
        self._subtask_products_model = subtask_products_model
        self._subtask_products_proxy_model = subtask_products_proxy_model

        self._creators_model = creators_model
        self._creators_sort_model = creators_sort_model
        self._creators_view = creators_view
        self._create_btn = create_btn

        self._creator_short_desc_widget = creator_short_desc_widget
        self._creator_basics_widget = creator_basics_widget
        self._thumbnail_widget = thumbnail_widget
        self._pre_create_widget = pre_create_widget
        self._attr_separator_widget = attr_separator_widget

        self._prereq_timer = prereq_timer
        self._first_show = True
        self._last_thumbnail_path = None

        self._current_subtask_product = None
        self._last_current_context_folder_path = None
        self._last_current_context_task = None
        self._use_current_context = True
        self._current_creator_variant_hints = []

    def get_current_folder_path(self) -> str | None:
        return self._controller.get_current_folder_path()

    def get_current_task_name(self) -> str | None:
        return self._controller.get_current_task_name()

    def _context_change_is_enabled(self) -> bool:
        return self._context_widget.is_enabled()

    def _get_folder_path(self) -> str | None:
        folder_path = None
        if self._context_change_is_enabled():
            folder_path = self._context_widget.get_selected_folder_path()
        return folder_path or None

    def _get_folder_id(self) -> str | None:
        folder_id = None
        if self._context_widget.is_enabled():
            folder_id = self._context_widget.get_selected_folder_id()
        return folder_id

    def _get_task_name(self) -> str | None:
        task_name = None
        if self._context_change_is_enabled():
            # Don't use selection of task if folder is not set
            folder_path = self._context_widget.get_selected_folder_path()
            if folder_path:
                task_name = self._context_widget.get_selected_task_name()
        return task_name

    def _set_context_enabled(self, enabled: bool) -> None:
        check_prereq = self._context_widget.is_enabled() != enabled
        self._context_widget.set_enabled(enabled)
        if check_prereq:
            self._invalidate_prereq()

    def _on_main_window_close(self) -> None:
        """Publisher window was closed."""

        # Use current context on next refresh
        self._use_current_context = True

    def refresh(self) -> None:
        current_folder_path = self._controller.get_current_folder_path()
        current_task_name = self._controller.get_current_task_name()

        # Get context before refresh to keep selection of folder and
        #   task widgets
        folder_path = self._get_folder_path()
        task_name = self._get_task_name()

        # Replace by current context if last loaded context was
        #   'current context' before reset
        if (
            self._use_current_context
            or (
                self._last_current_context_folder_path
                and folder_path == self._last_current_context_folder_path
                and task_name == self._last_current_context_task
            )
        ):
            folder_path = current_folder_path
            task_name = current_task_name

        # Store values for future refresh
        self._last_current_context_folder_path = current_folder_path
        self._last_current_context_task = current_task_name
        self._use_current_context = False

        self._prereq_available = False

        # Disable context widget so refresh of folder will use context folder
        #   path
        self._set_context_enabled(False)

        # Refresh data before update of creators
        self._context_widget.refresh()
        self._refresh_product_name()

        self._refresh_subtask_products()
        # Then refresh creators which may trigger callbacks using refreshed
        #   data
        self._refresh_creators()

        folder_id = self._controller.get_folder_id_from_path(folder_path)
        self._context_widget.update_current_context_btn()
        self._context_widget.set_selected_context(folder_id, task_name)

        self._invalidate_prereq_deffered()

    def _invalidate_prereq_deffered(self) -> None:
        self._prereq_timer.start()

    def _invalidate_prereq(self) -> None:
        prereq_available = True
        creator_btn_tooltips = []

        available_creators = self._creators_model.rowCount() > 0
        if available_creators != self._creators_view.isEnabled():
            self._creators_view.setEnabled(available_creators)

        if not available_creators:
            prereq_available = False
            creator_btn_tooltips.append("Creator is not selected")

        if (
            self._context_change_is_enabled()
            and self._get_folder_path() is None
        ):
            # QUESTION how to handle invalid folder?
            prereq_available = False
            creator_btn_tooltips.append("Context is not selected")

        self._prereq_available = prereq_available
        self._create_btn.setEnabled(prereq_available)
        self._variant_widget.setEnabled(prereq_available)

        tooltip = ""
        if creator_btn_tooltips:
            tooltip = "\n".join(creator_btn_tooltips)
        self._create_btn.setToolTip(tooltip)

        self._on_variant_change()

    def _refresh_product_name(self) -> None:
        folder_path = self._get_folder_path()

        # Skip if folder did not change
        if self._folder_path and self._folder_path == folder_path:
            return

        # Make sure `_folder_path` and `_product_names` variables are reset
        self._folder_path = folder_path
        self._product_names = None
        if folder_path is None:
            return

        product_names = self._controller.get_existing_product_names(
            folder_path
        )

        self._product_names = product_names
        if product_names is None:
            self.product_name_input.setText("< Folder is not set >")

    def _refresh_subtask_products(self) -> None:
        folder_id = self._get_folder_id()
        task_name = self._get_task_name()
        subtask_products = []
        if folder_id and task_name:
            subtask_products = self._controller.get_subtask_products(
                folder_id, task_name
            )

        root_item = self._subtask_products_model.invisibleRootItem()
        if not subtask_products:
            root_item.removeRows(0, root_item.rowCount())
            self._subtask_products_widget.setVisible(False)
            self._current_subtask_product = None
            return

        icon_created = get_qt_icon(
            MaterialSymbolsIcon("check_circle", color="#37DFAC")
        )
        icon_missing = get_qt_icon(
            MaterialSymbolsIcon("pending", color="#515661")
        )
        self._subtask_products_widget.setVisible(True)

        # Refresh creators and add their product base types to list
        existing_items = {}
        for row in range(root_item.rowCount()):
            item = root_item.child(row, 0)
            product_name = item.data(SUBTASK_PRODUCT_NAME_ROLE)
            existing_items[product_name] = item

        new_items = []
        for idx, subtask_product in enumerate(subtask_products):
            item = existing_items.pop(subtask_product.product_name, None)
            if item is None:
                item = QtGui.QStandardItem(subtask_product.product_name)
                new_items.append(item)

            for value, role in (
                (idx, SUBTASK_PRODUCT_SORT_ROLE),
                (subtask_product.product_name, SUBTASK_PRODUCT_NAME_ROLE),
                (subtask_product.product_type, SUBTASK_PRODUCT_TYPE_ROLE),
                (subtask_product.created, SUBTASK_PRODUCT_CREATED_ROLE),
                (
                    subtask_product.product_base_type,
                    SUBTASK_PRODUCT_BASE_TYPE_ROLE
                ),
            ):
                item.setData(value, role)

            icon = icon_created
            flags = QtCore.Qt.ItemIsEnabled
            if not subtask_product.created:
                icon = icon_missing
                flags |= QtCore.Qt.ItemIsSelectable

            item.setFlags(flags)
            item.setData(icon, QtCore.Qt.DecorationRole)

        for item in existing_items.values():
            root_item.removeRow(item.row())

        if new_items:
            root_item.appendRows(new_items)

        self._subtask_products_proxy_model.sort(0)

        self._update_subtask_selection()

    def _update_subtask_selection(self) -> None:
        selected_index = next(
            iter(self._subtask_products_view.selectedIndexes()),
            None
        )

        if (
            selected_index is not None
            and not selected_index.flags() & QtCore.Qt.ItemIsSelectable
        ):
            selected_index = None

        if self._current_subtask_product is None:
            if selected_index is not None:
                self._on_subtask_product_change(
                    selected_index, QtCore.QModelIndex()
                )
            return

        if selected_index is not None:
            self._on_subtask_product_change(
                selected_index, QtCore.QModelIndex()
            )
            return
        next_selection = None
        for row in range(self._subtask_products_proxy_model.rowCount()):
            index = self._subtask_products_proxy_model.index(row, 0)
            if not index.flags() & QtCore.Qt.ItemIsSelectable:
                continue

            product_name = index.data(SUBTASK_PRODUCT_NAME_ROLE)
            if product_name == self._current_subtask_product.product_name:
                next_selection = index
                break

            if next_selection is None:
                next_selection = index

        if next_selection is None:
            next_selection = QtCore.QModelIndex()

        self._subtask_products_view.setCurrentIndex(next_selection)
        self._on_subtask_product_change(
            next_selection, QtCore.QModelIndex()
        )

    def _refresh_creators(self) -> None:
        # Refresh creators and add their product base types to list
        existing_items = collections.defaultdict(dict)
        for row in range(self._creators_model.rowCount()):
            item = self._creators_model.item(row, 0)
            identifier = item.data(CREATOR_IDENTIFIER_ROLE)
            product_type = item.data(PRODUCT_TYPE_ROLE)
            existing_items[identifier][product_type] = item

        # Add new create plugins
        new_creators = collections.defaultdict(set)
        creator_items_by_identifier = self._controller.get_creator_items()
        for identifier, creator_item in creator_items_by_identifier.items():
            if creator_item.creator_type != "artist":
                continue

            # TODO add details about creator
            for ui_item in creator_item.ui_items:
                if ui_item.filtered:
                    continue

                items_by_identifier = new_creators[identifier]
                items_by_identifier.add(ui_item.product_type)
                is_new = False
                item = existing_items[identifier].get(ui_item.product_type)
                if item is None:
                    is_new = True
                    item = QtGui.QStandardItem()
                    item.setFlags(
                        QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
                    )

                item.setData(ui_item.label, QtCore.Qt.DisplayRole)
                item.setData(creator_item.show_order, CREATOR_SORT_ROLE)
                item.setData(identifier, CREATOR_IDENTIFIER_ROLE)
                item.setData(
                    creator_item.product_base_type,
                    PRODUCT_BASE_TYPE_ROLE
                )
                item.setData(ui_item.product_type, PRODUCT_TYPE_ROLE)
                item.setData(
                    creator_item.create_allow_thumbnail,
                    CREATOR_THUMBNAIL_ENABLED_ROLE
                )
                if is_new:
                    self._creators_model.appendRow(item)

        # Remove create plugins that are no more available
        for identifier, items_by_pt in existing_items.items():
            n_product_types = new_creators[identifier]
            for product_type, item in items_by_pt.items():
                if product_type not in n_product_types:
                    self._creators_model.takeRow(item.row())

        if self._creators_model.rowCount() < 1:
            return

        self._creators_sort_model.sort(0)
        # Make sure there is a selection
        indexes = self._creators_view.selectedIndexes()
        if not indexes:
            index = self._creators_sort_model.index(0, 0)
            self._creators_view.setCurrentIndex(index)
        else:
            index = indexes[0]

        identifier = index.data(CREATOR_IDENTIFIER_ROLE)
        product_type = index.data(PRODUCT_TYPE_ROLE)
        create_item = creator_items_by_identifier.get(identifier)

        self._set_creator(create_item, product_type)

    def _on_controler_reset(self) -> None:
        # Trigger refresh only if is visible
        self.refresh()

    def _pre_create_attr_changed(self, event) -> None:
        if (
            self._selected_creator_identifier is None
            or self._selected_creator_identifier not in event["identifiers"]
        ):
            return

        self._set_creator_by_identifier(
            self._selected_creator_identifier,
            self._selected_product_type,
        )

    def _on_folder_change(self) -> None:
        self._refresh_product_name()
        if self._context_change_is_enabled():
            self._invalidate_prereq_deffered()

    def _on_task_change(self) -> None:
        if self._context_change_is_enabled():
            self._invalidate_prereq_deffered()
        self._refresh_subtask_products()

    def _on_thumbnail_create(self, thumbnail_path: str) -> None:
        self._last_thumbnail_path = thumbnail_path
        self._thumbnail_widget.set_current_thumbnails([thumbnail_path])

    def _on_thumbnail_clear(self) -> None:
        self._last_thumbnail_path = None

    def _on_subtask_product_change(self, new_index, _old_index) -> None:
        item = None
        if (
            new_index.isValid()
            and new_index.flags() & QtCore.Qt.ItemIsSelectable
        ):
            product_name = new_index.data(SUBTASK_PRODUCT_NAME_ROLE)
            product_base_type = new_index.data(SUBTASK_PRODUCT_BASE_TYPE_ROLE)
            product_type = new_index.data(SUBTASK_PRODUCT_TYPE_ROLE)
            created = new_index.data(SUBTASK_PRODUCT_CREATED_ROLE)
            item = SubtaskProduct(
                product_name,
                product_base_type,
                product_type,
                created,
            )

        self._current_subtask_product = item
        self._creators_sort_model.set_subset_product_filter(item)

        if item is not None:
            self.product_name_input.setText(item.product_name)
            self._variant_widget.setEnabled(False)
            self._variant_widget.setText("")
            self._set_variant_state_property("")
        else:
            # Re-set creator item to update variant and product name
            identifier = self._selected_creator_identifier
            product_type = self._selected_product_type
            if self._selected_creator_identifier is None:
                index = self._creators_sort_model.index(0, 0)
                identifier = index.data(CREATOR_IDENTIFIER_ROLE)
                product_type = index.data(PRODUCT_TYPE_ROLE)

            self._set_creator_by_identifier(identifier, product_type)
            # Run invalidation of pre-requirements to update state
            #   of variant input and create button
            self._invalidate_prereq()

        if item is not None:
            creator_index = QtCore.QModelIndex()
            # Select first creator with matching product base type
            for row in range(self._creators_sort_model.rowCount()):
                index = self._creators_sort_model.index(row, 0)
                flags = self._creators_sort_model.flags(index)
                if flags & QtCore.Qt.ItemIsEnabled:
                    creator_index = index
                    break
            self._creators_view.setCurrentIndex(creator_index)

    def _on_creator_item_change(self, new_index, _old_index) -> None:
        identifier = None
        product_type = None
        if new_index.isValid():
            identifier = new_index.data(CREATOR_IDENTIFIER_ROLE)
            product_type = new_index.data(PRODUCT_TYPE_ROLE)
        self._set_creator_by_identifier(identifier, product_type)

    def _set_creator_detailed_text(
        self, creator_item: CreatorItem | None
    ) -> None:
        # TODO implement
        description = ""
        if creator_item is not None:
            description = creator_item.detailed_description or description
        self._controller.emit_event(
            "show.detailed.help",
            {
                "message": description
            },
            "create.widget"
        )

    def _set_creator_by_identifier(
        self,
        identifier: str | None,
        product_type: str | None,
    ) -> None:
        creator_item = self._controller.get_creator_item_by_id(
            identifier
        )
        self._set_creator(creator_item, product_type)

    def _set_creator(
        self,
        creator_item: CreatorItem | None,
        product_type: str | None,
    ) -> None:
        """Set current creator item.

        Args:
            creator_item (CreatorItem): Item representing creator that can be
                triggered by artist.
            product_type (str): Product type of creator item.

        """
        self._creator_short_desc_widget.set_creator_item(
            creator_item, product_type
        )
        self._set_creator_detailed_text(creator_item)
        self._pre_create_widget.set_creator_item(creator_item)

        if not creator_item:
            self._selected_creator_identifier = None
            self._selected_product_type = None
            if self._current_subtask_product is None:
                self._set_context_enabled(False)
            self._create_btn.setEnabled(False)
            return

        self._create_btn.setEnabled(True)

        self._selected_creator_identifier = creator_item.identifier
        self._selected_product_type = product_type

        if (
            creator_item.create_allow_context_change
            != self._context_change_is_enabled()
        ):
            self._set_context_enabled(creator_item.create_allow_context_change)
            self._refresh_product_name()

        self._thumbnail_widget.setVisible(
            creator_item.create_allow_thumbnail
        )

        default_variants = creator_item.default_variants
        if not default_variants:
            default_variants = [DEFAULT_VARIANT_VALUE]

        default_variant = creator_item.default_variant
        if not default_variant:
            default_variant = default_variants[0]

        self._current_creator_variant_hints = list(default_variants)
        self._variant_widget.set_options(default_variants)

        variant_text = default_variant or DEFAULT_VARIANT_VALUE
        # Make sure product name is updated to new plugin
        if variant_text == self._variant_widget.text():
            self._on_variant_change()
        else:
            self._variant_widget.setText(variant_text)

    def _on_variant_change(self, variant_value: str | None = None) -> None:
        if not self._prereq_available:
            return

        if self._current_subtask_product is not None:
            return

        # This should probably never happen?
        if not self._selected_creator_identifier:
            if self.product_name_input.text():
                self.product_name_input.setText("")
            return

        if variant_value is None:
            variant_value = self._variant_widget.text()

        if not self._compiled_name_pattern.match(variant_value):
            self._create_btn.setEnabled(False)
            self._set_variant_state_property("invalid")
            self.product_name_input.setText("< Invalid variant >")
            return

        if not self._context_change_is_enabled():
            self._create_btn.setEnabled(True)
            self._set_variant_state_property("")
            self.product_name_input.setText("< Valid variant >")
            return

        folder_path = self._get_folder_path()
        task_name = self._get_task_name()
        # Calculate product name with Creator plugin
        try:
            product_name = self._controller.get_product_name(
                self._selected_creator_identifier,
                self._selected_product_type,
                variant_value,
                folder_path,
                task_name,
            )
        except TaskNotSetError:
            self._create_btn.setEnabled(False)
            self._set_variant_state_property("invalid")
            self.product_name_input.setText("< Missing task >")
            return

        self.product_name_input.setText(product_name)

        self._create_btn.setEnabled(True)
        self._validate_product_name(product_name, variant_value)

    def _validate_product_name(
        self, product_name: str, variant_value: str
    ) -> None:
        # Get all products of the current folder
        if self._product_names:
            existing_product_names = set(self._product_names)
        else:
            existing_product_names = set()
        existing_product_names_low = set(
            _name.lower()
            for _name in existing_product_names
        )

        # Replace
        compare_regex = re.compile(re.sub(
            variant_value, "(.+)", product_name, flags=re.IGNORECASE
        ))
        variant_hints = set()
        if variant_value:
            for _name in existing_product_names:
                _result = compare_regex.search(_name)
                if _result:
                    variant_hints |= set(_result.groups())

        options = list(self._current_creator_variant_hints)
        if options:
            options.append("---")
        options.extend(sorted(variant_hints))
        # Add hints to actions
        self._variant_widget.set_options(options)

        # Indicate product existence
        if not variant_value:
            property_value = "empty"

        elif product_name.lower() in existing_product_names_low:
            # validate existence of product name with lowered text
            #   - "renderMain" vs. "rendermain" mean same path item for
            #   windows
            property_value = "exists"
        else:
            property_value = "new"

        self._set_variant_state_property(property_value)

        variant_is_valid = variant_value.strip() != ""
        if variant_is_valid != self._create_btn.isEnabled():
            self._create_btn.setEnabled(variant_is_valid)

    def _set_variant_state_property(self, state: str) -> None:
        # "" | "empty" | "exists" | "new" | "invalid"
        self._variant_widget.set_text_widget_property("state", state)

    def _on_first_show(self) -> None:
        width = self.width()
        part = int(width / 9)
        context_width = part * 3
        create_sel_width = part * 2
        rem_width = width - context_width
        self._main_splitter_widget.setSizes([context_width, rem_width])
        rem_width -= create_sel_width
        self._creators_splitter.setSizes([create_sel_width, rem_width])

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
            self._on_first_show()

    def _on_creator_basics_resize(self) -> None:
        self._thumbnail_widget.set_height(
            self._creator_basics_widget.sizeHint().height()
        )

    def _on_instances_removed(self):
        self._refresh_subtask_products()

    def _on_create(self) -> None:
        indexes = self._creators_view.selectedIndexes()
        if not indexes or len(indexes) > 1:
            return

        if not self._create_btn.isEnabled():
            return

        index = indexes[0]
        creator_identifier = index.data(CREATOR_IDENTIFIER_ROLE)
        # Care about product name only if context change is enabled
        product_name = None
        folder_path = None
        task_name = None
        if self._context_change_is_enabled():
            product_name = self.product_name_input.text()
            folder_path = self._get_folder_path()
            task_name = self._get_task_name()

        variant = self._variant_widget.text()
        if self._current_subtask_product is None:
            product_type = index.data(PRODUCT_TYPE_ROLE)
            product_base_type = index.data(PRODUCT_BASE_TYPE_ROLE)

        else:
            product_name = self._current_subtask_product.product_name
            product_type = self._current_subtask_product.product_type
            product_base_type = (
                self._current_subtask_product.product_base_type
            )

        pre_create_data = self._pre_create_widget.current_value()
        if index.data(CREATOR_THUMBNAIL_ENABLED_ROLE):
            pre_create_data[PRE_CREATE_THUMBNAIL_KEY] = (
                self._last_thumbnail_path
            )

        # Where to define these data?
        # - what data show be stored?
        instance_data = {
            "folderPath": folder_path,
            "task": task_name,
            "variant": variant,
            "productBaseType": product_base_type,
            "productType": product_type,
        }

        success = self._controller.create(
            creator_identifier,
            product_name,
            instance_data,
            pre_create_data
        )

        if not success:
            return

        # TODO handle case when subtask product was selected
        # - probably select next one?
        self._refresh_subtask_products()
        self._set_creator_by_identifier(
            self._selected_creator_identifier,
            self._selected_product_type,
        )
        self._variant_widget.setText(variant)
        self._controller.emit_card_message("Creation finished...")
        self._last_thumbnail_path = None
        self._thumbnail_widget.set_current_thumbnails()
