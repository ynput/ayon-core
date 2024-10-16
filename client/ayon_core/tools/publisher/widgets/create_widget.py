import re

from qtpy import QtWidgets, QtCore, QtGui

from ayon_core.pipeline.create import (
    PRODUCT_NAME_ALLOWED_SYMBOLS,
    PRE_CREATE_THUMBNAIL_KEY,
    DEFAULT_VARIANT_VALUE,
    TaskNotSetError,
)

from ayon_core.tools.publisher.abstract import AbstractPublisherFrontend
from ayon_core.tools.publisher.constants import (
    VARIANT_TOOLTIP,
    PRODUCT_TYPE_ROLE,
    CREATOR_IDENTIFIER_ROLE,
    CREATOR_THUMBNAIL_ENABLED_ROLE,
    CREATOR_SORT_ROLE,
    INPUTS_LAYOUT_HSPACING,
    INPUTS_LAYOUT_VSPACING,
)
from ayon_core.tools.utils import HintedLineEdit

from .thumbnail_widget import ThumbnailWidget
from .widgets import (
    IconValuePixmapLabel,
    CreateBtn,
)
from .create_context_widgets import CreateContextWidget
from .precreate_widget import PreCreateWidget


class ResizeControlWidget(QtWidgets.QWidget):
    resized = QtCore.Signal()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resized.emit()


# TODO add creator identifier/label to details
class CreatorShortDescWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

        # --- Short description widget ---
        icon_widget = IconValuePixmapLabel(None, self)
        icon_widget.setObjectName("ProductTypeIconLabel")

        # --- Short description inputs ---
        short_desc_input_widget = QtWidgets.QWidget(self)

        product_type_label = QtWidgets.QLabel(short_desc_input_widget)
        product_type_label.setAlignment(
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
        short_desc_input_layout.addWidget(product_type_label)
        short_desc_input_layout.addWidget(description_label)
        # --------------------------------

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(icon_widget, 0)
        layout.addWidget(short_desc_input_widget, 1)
        # --------------------------------

        self._icon_widget = icon_widget
        self._product_type_label = product_type_label
        self._description_label = description_label

    def set_creator_item(self, creator_item=None):
        if not creator_item:
            self._icon_widget.set_icon_def(None)
            self._product_type_label.setText("")
            self._description_label.setText("")
            return

        plugin_icon = creator_item.icon
        description = creator_item.description or ""

        self._icon_widget.set_icon_def(plugin_icon)
        self._product_type_label.setText("<b>{}</b>".format(creator_item.product_type))
        self._product_type_label.setTextInteractionFlags(QtCore.Qt.NoTextInteraction)
        self._description_label.setText(description)


class CreatorsProxyModel(QtCore.QSortFilterProxyModel):
    def lessThan(self, left, right):
        l_show_order = left.data(CREATOR_SORT_ROLE)
        r_show_order = right.data(CREATOR_SORT_ROLE)
        if l_show_order == r_show_order:
            return super().lessThan(left, right)
        return l_show_order < r_show_order


class CreateWidget(QtWidgets.QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)

        self._controller: AbstractPublisherFrontend = controller

        self._folder_path = None
        self._product_names = None
        self._selected_creator_identifier = None

        self._prereq_available = False

        name_pattern = "^[{}]*$".format(PRODUCT_NAME_ALLOWED_SYMBOLS)
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
        pre_create_widget = PreCreateWidget(creators_attrs_widget)

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

        self._main_splitter_widget = main_splitter_widget

        self._creators_splitter = creators_splitter

        self._context_widget = context_widget

        self.product_name_input = product_name_input

        self._variant_widget = variant_widget

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

        self._last_current_context_folder_path = None
        self._last_current_context_task = None
        self._use_current_context = True
        self._current_creator_variant_hints = []

    def get_current_folder_path(self):
        return self._controller.get_current_folder_path()

    def get_current_task_name(self):
        return self._controller.get_current_task_name()

    def _context_change_is_enabled(self):
        return self._context_widget.is_enabled()

    def _get_folder_path(self):
        folder_path = None
        if self._context_change_is_enabled():
            folder_path = self._context_widget.get_selected_folder_path()

        if folder_path is None:
            folder_path = self.get_current_folder_path()
        return folder_path or None

    def _get_folder_id(self):
        folder_id = None
        if self._context_widget.is_enabled():
            folder_id = self._context_widget.get_selected_folder_id()
        return folder_id

    def _get_task_name(self):
        task_name = None
        if self._context_change_is_enabled():
            # Don't use selection of task if folder is not set
            folder_path = self._context_widget.get_selected_folder_path()
            if folder_path:
                task_name = self._context_widget.get_selected_task_name()

        if not task_name:
            task_name = self.get_current_task_name()
        return task_name

    def _set_context_enabled(self, enabled):
        check_prereq = self._context_widget.is_enabled() != enabled
        self._context_widget.set_enabled(enabled)
        if check_prereq:
            self._invalidate_prereq()

    def _on_main_window_close(self):
        """Publisher window was closed."""

        # Use current context on next refresh
        self._use_current_context = True

    def refresh(self):
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

        # Then refresh creators which may trigger callbacks using refreshed
        #   data
        self._refresh_creators()

        folder_id = self._controller.get_folder_id_from_path(folder_path)
        self._context_widget.update_current_context_btn()
        self._context_widget.set_selected_context(folder_id, task_name)

        self._invalidate_prereq_deffered()

    def _invalidate_prereq_deffered(self):
        self._prereq_timer.start()

    def _invalidate_prereq(self):
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

        if prereq_available != self._prereq_available:
            self._prereq_available = prereq_available

            self._create_btn.setEnabled(prereq_available)

            self._variant_widget.setEnabled(prereq_available)

        tooltip = ""
        if creator_btn_tooltips:
            tooltip = "\n".join(creator_btn_tooltips)
        self._create_btn.setToolTip(tooltip)

        self._on_variant_change()

    def _refresh_product_name(self):
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

    def _refresh_creators(self):
        # Refresh creators and add their product types to list
        existing_items = {}
        old_creators = set()
        for row in range(self._creators_model.rowCount()):
            item = self._creators_model.item(row, 0)
            identifier = item.data(CREATOR_IDENTIFIER_ROLE)
            existing_items[identifier] = item
            old_creators.add(identifier)

        # Add new create plugins
        new_creators = set()
        creator_items_by_identifier = self._controller.get_creator_items()
        for identifier, creator_item in creator_items_by_identifier.items():
            if creator_item.creator_type != "artist":
                continue

            # TODO add details about creator
            new_creators.add(identifier)
            if identifier in existing_items:
                is_new = False
                item = existing_items[identifier]
            else:
                is_new = True
                item = QtGui.QStandardItem()
                item.setFlags(
                    QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
                )

            item.setData(creator_item.label, QtCore.Qt.DisplayRole)
            item.setData(creator_item.show_order, CREATOR_SORT_ROLE)
            item.setData(identifier, CREATOR_IDENTIFIER_ROLE)
            item.setData(
                creator_item.create_allow_thumbnail,
                CREATOR_THUMBNAIL_ENABLED_ROLE
            )
            item.setData(creator_item.product_type, PRODUCT_TYPE_ROLE)
            if is_new:
                self._creators_model.appendRow(item)

        # Remove create plugins that are no more available
        for identifier in (old_creators - new_creators):
            item = existing_items[identifier]
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
        create_item = creator_items_by_identifier.get(identifier)

        self._set_creator(create_item)

    def _on_controler_reset(self):
        # Trigger refresh only if is visible
        self.refresh()

    def _pre_create_attr_changed(self, event):
        if (
            self._selected_creator_identifier is None
            or self._selected_creator_identifier not in event["identifiers"]
        ):
            return

        self._set_creator_by_identifier(self._selected_creator_identifier)

    def _on_folder_change(self):
        self._refresh_product_name()
        if self._context_change_is_enabled():
            self._invalidate_prereq_deffered()

    def _on_task_change(self):
        if self._context_change_is_enabled():
            self._invalidate_prereq_deffered()

    def _on_thumbnail_create(self, thumbnail_path):
        self._last_thumbnail_path = thumbnail_path
        self._thumbnail_widget.set_current_thumbnails([thumbnail_path])

    def _on_thumbnail_clear(self):
        self._last_thumbnail_path = None

    def _on_creator_item_change(self, new_index, _old_index):
        identifier = None
        if new_index.isValid():
            identifier = new_index.data(CREATOR_IDENTIFIER_ROLE)
        self._set_creator_by_identifier(identifier)

    def _set_creator_detailed_text(self, creator_item):
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

    def _set_creator_by_identifier(self, identifier):
        creator_item = self._controller.get_creator_item_by_id(identifier)
        self._set_creator(creator_item)

    def _set_creator(self, creator_item):
        """Set current creator item.

        Args:
            creator_item (CreatorItem): Item representing creator that can be
                triggered by artist.
        """

        self._creator_short_desc_widget.set_creator_item(creator_item)
        self._set_creator_detailed_text(creator_item)
        self._pre_create_widget.set_creator_item(creator_item)

        if not creator_item:
            self._selected_creator_identifier = None
            self._set_context_enabled(False)
            return

        self._selected_creator_identifier = creator_item.identifier

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

    def _on_variant_change(self, variant_value=None):
        if not self._prereq_available:
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
                variant_value,
                task_name,
                folder_path
            )
        except TaskNotSetError:
            self._create_btn.setEnabled(False)
            self._set_variant_state_property("invalid")
            self.product_name_input.setText("< Missing task >")
            return

        self.product_name_input.setText(product_name)

        self._create_btn.setEnabled(True)
        self._validate_product_name(product_name, variant_value)

    def _validate_product_name(self, product_name, variant_value):
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
        options.extend(variant_hints)
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

    def _set_variant_state_property(self, state):
        self._variant_widget.set_text_widget_property("state", state)

    def _on_first_show(self):
        width = self.width()
        part = int(width / 4)
        rem_width = width - part
        self._main_splitter_widget.setSizes([part, rem_width])
        rem_width = rem_width - part
        self._creators_splitter.setSizes([part, rem_width])

    def showEvent(self, event):
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
            self._on_first_show()

    def _on_creator_basics_resize(self):
        self._thumbnail_widget.set_height(
            self._creator_basics_widget.sizeHint().height()
        )

    def _on_create(self):
        indexes = self._creators_view.selectedIndexes()
        if not indexes or len(indexes) > 1:
            return

        if not self._create_btn.isEnabled():
            return

        index = indexes[0]
        creator_identifier = index.data(CREATOR_IDENTIFIER_ROLE)
        product_type = index.data(PRODUCT_TYPE_ROLE)
        variant = self._variant_widget.text()
        # Care about product name only if context change is enabled
        product_name = None
        folder_path = None
        task_name = None
        if self._context_change_is_enabled():
            product_name = self.product_name_input.text()
            folder_path = self._get_folder_path()
            task_name = self._get_task_name()

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
            "productType": product_type
        }

        success = self._controller.create(
            creator_identifier,
            product_name,
            instance_data,
            pre_create_data
        )

        if success:
            self._set_creator_by_identifier(self._selected_creator_identifier)
            self._variant_widget.setText(variant)
            self._controller.emit_card_message("Creation finished...")
            self._last_thumbnail_path = None
            self._thumbnail_widget.set_current_thumbnails()
