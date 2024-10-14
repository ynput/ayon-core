import re
import copy
import collections

from qtpy import QtWidgets, QtCore, QtGui
import qtawesome

from ayon_core.pipeline.create import (
    PRODUCT_NAME_ALLOWED_SYMBOLS,
    TaskNotSetError,
)
from ayon_core.tools.utils import (
    PlaceholderLineEdit,
    BaseClickableFrame,
    set_style_property,
)
from ayon_core.tools.publisher.abstract import AbstractPublisherFrontend
from ayon_core.tools.publisher.constants import (
    VARIANT_TOOLTIP,
    INPUTS_LAYOUT_HSPACING,
    INPUTS_LAYOUT_VSPACING,
)

from .folders_dialog import FoldersDialog
from .tasks_model import TasksModel
from .widgets import ClickableLineEdit, MultipleItemWidget


class FoldersFields(BaseClickableFrame):
    """Field where folder path of selected instance/s is showed.

    Click on the field will trigger `FoldersDialog`.
    """
    value_changed = QtCore.Signal()

    def __init__(
        self, controller: AbstractPublisherFrontend, parent: QtWidgets.QWidget
    ):
        super().__init__(parent)
        self.setObjectName("FolderPathInputWidget")

        # Don't use 'self' for parent!
        # - this widget has specific styles
        dialog = FoldersDialog(controller, parent)

        name_input = ClickableLineEdit(self)
        name_input.setObjectName("FolderPathInput")

        icon_name = "fa.window-maximize"
        icon = qtawesome.icon(icon_name, color="white")
        icon_btn = QtWidgets.QPushButton(self)
        icon_btn.setIcon(icon)
        icon_btn.setObjectName("FolderPathInputButton")

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(name_input, 1)
        layout.addWidget(icon_btn, 0)

        # Make sure all widgets are vertically extended to highest widget
        for widget in (
            name_input,
            icon_btn
        ):
            size_policy = widget.sizePolicy()
            size_policy.setVerticalPolicy(
                QtWidgets.QSizePolicy.MinimumExpanding)
            widget.setSizePolicy(size_policy)
        name_input.clicked.connect(self._mouse_release_callback)
        icon_btn.clicked.connect(self._mouse_release_callback)
        dialog.finished.connect(self._on_dialog_finish)

        self._controller: AbstractPublisherFrontend = controller
        self._dialog = dialog
        self._name_input = name_input
        self._icon_btn = icon_btn

        self._origin_value = []
        self._origin_selection = []
        self._selected_items = []
        self._has_value_changed = False
        self._is_valid = True
        self._multiselection_text = None

    def _on_dialog_finish(self, result):
        if not result:
            return

        folder_path = self._dialog.get_selected_folder_path()
        if folder_path is None:
            return

        self._selected_items = [folder_path]
        self._has_value_changed = (
            self._origin_value != self._selected_items
        )
        self.set_text(folder_path)
        self._set_is_valid(True)

        self.value_changed.emit()

    def _mouse_release_callback(self):
        self._dialog.set_selected_folders(self._selected_items)
        self._dialog.open()

    def set_multiselection_text(self, text):
        """Change text for multiselection of different folders.

        When there are selected multiple instances at once and they don't have
        same folder in context.
        """
        self._multiselection_text = text

    def _set_is_valid(self, valid):
        if valid == self._is_valid:
            return
        self._is_valid = valid
        state = ""
        if not valid:
            state = "invalid"
        self._set_state_property(state)

    def _set_state_property(self, state):
        set_style_property(self, "state", state)
        set_style_property(self._name_input, "state", state)
        set_style_property(self._icon_btn, "state", state)

    def is_valid(self):
        """Is folder valid."""
        return self._is_valid

    def has_value_changed(self):
        """Value of folder has changed."""
        return self._has_value_changed

    def get_selected_items(self):
        """Selected folder paths."""
        return list(self._selected_items)

    def set_text(self, text):
        """Set text in text field.

        Does not change selected items (folders).
        """
        self._name_input.setText(text)
        self._name_input.end(False)

    def set_selected_items(self, folder_paths=None):
        """Set folder paths for selection of instances.

        Passed folder paths are validated and if there are 2 or more different
        folder paths then multiselection text is shown.

        Args:
            folder_paths (list, tuple, set, NoneType): List of folder paths.

        """
        if folder_paths is None:
            folder_paths = []

        self._has_value_changed = False
        self._origin_value = list(folder_paths)
        self._selected_items = list(folder_paths)
        is_valid = self._controller.are_folder_paths_valid(folder_paths)
        if not folder_paths:
            self.set_text("")

        elif len(folder_paths) == 1:
            folder_path = tuple(folder_paths)[0]
            self.set_text(folder_path)
        else:
            multiselection_text = self._multiselection_text
            if multiselection_text is None:
                multiselection_text = "|".join(folder_paths)
            self.set_text(multiselection_text)

        self._set_is_valid(is_valid)

    def reset_to_origin(self):
        """Change to folder paths set with last `set_selected_items` call."""
        self.set_selected_items(self._origin_value)

    def confirm_value(self):
        self._origin_value = copy.deepcopy(self._selected_items)
        self._has_value_changed = False


class TasksComboboxProxy(QtCore.QSortFilterProxyModel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._filter_empty = False

    def set_filter_empty(self, filter_empty):
        if self._filter_empty is filter_empty:
            return
        self._filter_empty = filter_empty
        self.invalidate()

    def filterAcceptsRow(self, source_row, parent_index):
        if self._filter_empty:
            model = self.sourceModel()
            source_index = model.index(
                source_row, self.filterKeyColumn(), parent_index
            )
            if not source_index.data(QtCore.Qt.DisplayRole):
                return False
        return True


class TasksCombobox(QtWidgets.QComboBox):
    """Combobox to show tasks for selected instances.

    Combobox gives ability to select only from intersection of task names for
    folder paths in selected instances.

    If folder paths in selected instances does not have same tasks then combobox
    will be empty.
    """
    value_changed = QtCore.Signal()

    def __init__(
        self, controller: AbstractPublisherFrontend, parent: QtWidgets.QWidget
    ):
        super().__init__(parent)
        self.setObjectName("TasksCombobox")

        # Set empty delegate to propagate stylesheet to a combobox
        delegate = QtWidgets.QStyledItemDelegate()
        self.setItemDelegate(delegate)

        model = TasksModel(controller, True)
        proxy_model = TasksComboboxProxy()
        proxy_model.setSourceModel(model)
        self.setModel(proxy_model)

        self.currentIndexChanged.connect(self._on_index_change)

        self._delegate = delegate
        self._model = model
        self._proxy_model = proxy_model
        self._origin_value = []
        self._origin_selection = []
        self._selected_items = []
        self._has_value_changed = False
        self._ignore_index_change = False
        self._multiselection_text = None
        self._is_valid = True

        self._text = None

        # Make sure combobox is extended horizontally
        size_policy = self.sizePolicy()
        size_policy.setHorizontalPolicy(
            QtWidgets.QSizePolicy.MinimumExpanding)
        self.setSizePolicy(size_policy)

    def set_invalid_empty_task(self, invalid=True):
        self._proxy_model.set_filter_empty(invalid)
        if invalid:
            self._set_is_valid(False)
            self.set_text(
                "< One or more products require Task selected >"
            )
        else:
            self.set_text(None)

    def set_multiselection_text(self, text):
        """Change text shown when multiple different tasks are in context."""
        self._multiselection_text = text

    def _on_index_change(self):
        if self._ignore_index_change:
            return

        self.set_text(None)
        text = self.currentText()
        idx = self.findText(text)
        if idx < 0:
            return

        self._set_is_valid(True)
        self._selected_items = [text]
        self._has_value_changed = (
            self._origin_selection != self._selected_items
        )

        self.value_changed.emit()

    def set_text(self, text):
        """Set context shown in combobox without changing selected items."""
        if text == self._text:
            return

        self._text = text
        self.repaint()

    def paintEvent(self, event):
        """Paint custom text without using QLineEdit.

        The easiest way how to draw custom text in combobox and keep combobox
        properties and event handling.
        """
        painter = QtGui.QPainter(self)
        painter.setPen(self.palette().color(QtGui.QPalette.Text))
        opt = QtWidgets.QStyleOptionComboBox()
        self.initStyleOption(opt)
        if self._text is not None:
            opt.currentText = self._text

        style = self.style()
        style.drawComplexControl(
            QtWidgets.QStyle.CC_ComboBox, opt, painter, self
        )
        style.drawControl(
            QtWidgets.QStyle.CE_ComboBoxLabel, opt, painter, self
        )
        painter.end()

    def is_valid(self):
        """Are all selected items valid."""
        return self._is_valid

    def has_value_changed(self):
        """Did selection of task changed."""
        return self._has_value_changed

    def _set_is_valid(self, valid):
        if valid == self._is_valid:
            return
        self._is_valid = valid
        state = ""
        if not valid:
            state = "invalid"
        self._set_state_property(state)

    def _set_state_property(self, state):
        current_value = self.property("state")
        if current_value != state:
            self.setProperty("state", state)
            self.style().polish(self)

    def get_selected_items(self):
        """Get selected tasks.

        If value has changed then will return list with single item.

        Returns:
            list: Selected tasks.
        """
        return list(self._selected_items)

    def set_folder_paths(self, folder_paths):
        """Set folder paths for which should show tasks."""
        self._ignore_index_change = True

        self._model.set_folder_paths(folder_paths)
        self._proxy_model.set_filter_empty(False)
        self._proxy_model.sort(0)

        self._ignore_index_change = False

        # It is a bug if not exactly one folder got here
        if len(folder_paths) != 1:
            self.set_selected_item("")
            self._set_is_valid(False)
            return

        folder_path = tuple(folder_paths)[0]

        is_valid = False
        if self._selected_items:
            is_valid = True

        valid_task_names = []
        for task_name in self._selected_items:
            _is_valid = self._model.is_task_name_valid(folder_path, task_name)
            if _is_valid:
                valid_task_names.append(task_name)
            else:
                is_valid = _is_valid

        self._selected_items = valid_task_names
        if len(self._selected_items) == 0:
            self.set_selected_item("")

        elif len(self._selected_items) == 1:
            self.set_selected_item(self._selected_items[0])

        else:
            multiselection_text = self._multiselection_text
            if multiselection_text is None:
                multiselection_text = "|".join(self._selected_items)
            self.set_selected_item(multiselection_text)

        self._set_is_valid(is_valid)

    def confirm_value(self, folder_paths):
        new_task_name = self._selected_items[0]
        self._origin_value = [
            (folder_path, new_task_name)
            for folder_path in folder_paths
        ]
        self._origin_selection = copy.deepcopy(self._selected_items)
        self._has_value_changed = False

    def set_selected_items(self, folder_task_combinations=None):
        """Set items for selected instances.

        Args:
            folder_task_combinations (list): List of tuples. Each item in
                the list contain folder path and task name.
        """
        self._proxy_model.set_filter_empty(False)
        self._proxy_model.sort(0)

        if folder_task_combinations is None:
            folder_task_combinations = []

        task_names = set()
        task_names_by_folder_path = collections.defaultdict(set)
        for folder_path, task_name in folder_task_combinations:
            task_names.add(task_name)
            task_names_by_folder_path[folder_path].add(task_name)
        folder_paths = set(task_names_by_folder_path.keys())

        self._ignore_index_change = True

        self._model.set_folder_paths(folder_paths)

        self._has_value_changed = False

        self._origin_value = copy.deepcopy(folder_task_combinations)

        self._origin_selection = list(task_names)
        self._selected_items = list(task_names)
        # Reset current index
        self.setCurrentIndex(-1)
        is_valid = True
        if not task_names:
            self.set_selected_item("")

        elif len(task_names) == 1:
            task_name = tuple(task_names)[0]
            idx = self.findText(task_name)
            is_valid = not idx < 0
            if not is_valid and len(folder_paths) > 1:
                is_valid = self._validate_task_names_by_folder_paths(
                    task_names_by_folder_path
                )
            self.set_selected_item(task_name)

        else:
            for task_name in task_names:
                idx = self.findText(task_name)
                is_valid = not idx < 0
                if not is_valid:
                    break

            if not is_valid and len(folder_paths) > 1:
                is_valid = self._validate_task_names_by_folder_paths(
                    task_names_by_folder_path
                )
            multiselection_text = self._multiselection_text
            if multiselection_text is None:
                multiselection_text = "|".join(task_names)
            self.set_selected_item(multiselection_text)

        self._set_is_valid(is_valid)

        self._ignore_index_change = False

        self.value_changed.emit()

    def _validate_task_names_by_folder_paths(self, task_names_by_folder_path):
        for folder_path, task_names in task_names_by_folder_path.items():
            for task_name in task_names:
                if not self._model.is_task_name_valid(folder_path, task_name):
                    return False
        return True

    def set_selected_item(self, item_name):
        """Set task which is set on selected instance.

        Args:
            item_name(str): Task name which should be selected.
        """
        idx = self.findText(item_name)
        # Set current index (must be set to -1 if is invalid)
        self.setCurrentIndex(idx)
        self.set_text(item_name)

    def reset_to_origin(self):
        """Change to task names set with last `set_selected_items` call."""
        self.set_selected_items(self._origin_value)


class VariantInputWidget(PlaceholderLineEdit):
    """Input widget for variant."""
    value_changed = QtCore.Signal()

    def __init__(self, parent):
        super().__init__(parent)

        self.setObjectName("VariantInput")
        self.setToolTip(VARIANT_TOOLTIP)

        name_pattern = "^[{}]*$".format(PRODUCT_NAME_ALLOWED_SYMBOLS)
        self._name_pattern = name_pattern
        self._compiled_name_pattern = re.compile(name_pattern)

        self._origin_value = []
        self._current_value = []

        self._ignore_value_change = False
        self._has_value_changed = False
        self._multiselection_text = None

        self._is_valid = True

        self.textChanged.connect(self._on_text_change)

    def is_valid(self):
        """Is variant text valid."""
        return self._is_valid

    def has_value_changed(self):
        """Value of variant has changed."""
        return self._has_value_changed

    def _set_state_property(self, state):
        current_value = self.property("state")
        if current_value != state:
            self.setProperty("state", state)
            self.style().polish(self)

    def set_multiselection_text(self, text):
        """Change text of multiselection."""
        self._multiselection_text = text

    def confirm_value(self):
        self._origin_value = copy.deepcopy(self._current_value)
        self._has_value_changed = False

    def _set_is_valid(self, valid):
        if valid == self._is_valid:
            return
        self._is_valid = valid
        state = ""
        if not valid:
            state = "invalid"
        self._set_state_property(state)

    def _on_text_change(self):
        if self._ignore_value_change:
            return

        is_valid = bool(self._compiled_name_pattern.match(self.text()))
        self._set_is_valid(is_valid)

        self._current_value = [self.text()]
        self._has_value_changed = self._current_value != self._origin_value

        self.value_changed.emit()

    def reset_to_origin(self):
        """Set origin value of selected instances."""
        self.set_value(self._origin_value)

    def get_value(self):
        """Get current value.

        Origin value returned if didn't change.
        """
        return copy.deepcopy(self._current_value)

    def set_value(self, variants=None):
        """Set value of currently selected instances."""
        if variants is None:
            variants = []

        self._ignore_value_change = True

        self._has_value_changed = False

        self._origin_value = list(variants)
        self._current_value = list(variants)

        self.setPlaceholderText("")
        if not variants:
            self.setText("")

        elif len(variants) == 1:
            self.setText(self._current_value[0])

        else:
            multiselection_text = self._multiselection_text
            if multiselection_text is None:
                multiselection_text = "|".join(variants)
            self.setText("")
            self.setPlaceholderText(multiselection_text)

        self._ignore_value_change = False


class GlobalAttrsWidget(QtWidgets.QWidget):
    """Global attributes mainly to define context and product name of instances.

    product name is or may be affected on context. Gives abiity to modify
    context and product name of instance. This change is not autopromoted but
    must be submitted.

    Warning: Until artist hit `Submit` changes must not be propagated to
    instance data.

    Global attributes contain these widgets:
    Variant:      [  text input  ]
    Folder:       [ folder dialog ]
    Task:         [   combobox   ]
    Product type: [   immutable  ]
    product name: [   immutable  ]
                     [Submit] [Cancel]
    """

    multiselection_text = "< Multiselection >"
    unknown_value = "N/A"

    def __init__(
        self, controller: AbstractPublisherFrontend, parent: QtWidgets.QWidget
    ):
        super().__init__(parent)

        self._controller: AbstractPublisherFrontend = controller
        self._current_instances_by_id = {}
        self._invalid_task_item_ids = set()

        variant_input = VariantInputWidget(self)
        folder_value_widget = FoldersFields(controller, self)
        task_value_widget = TasksCombobox(controller, self)
        product_type_value_widget = MultipleItemWidget(self)
        product_value_widget = MultipleItemWidget(self)

        variant_input.set_multiselection_text(self.multiselection_text)
        folder_value_widget.set_multiselection_text(self.multiselection_text)
        task_value_widget.set_multiselection_text(self.multiselection_text)

        variant_input.set_value()
        folder_value_widget.set_selected_items()
        task_value_widget.set_selected_items()
        product_type_value_widget.set_value()
        product_value_widget.set_value()

        submit_btn = QtWidgets.QPushButton("Confirm", self)
        cancel_btn = QtWidgets.QPushButton("Cancel", self)
        submit_btn.setEnabled(False)
        cancel_btn.setEnabled(False)

        btns_layout = QtWidgets.QHBoxLayout()
        btns_layout.setContentsMargins(0, 0, 0, 0)
        btns_layout.addStretch(1)
        btns_layout.setSpacing(5)
        btns_layout.addWidget(submit_btn)
        btns_layout.addWidget(cancel_btn)

        main_layout = QtWidgets.QFormLayout(self)
        main_layout.setHorizontalSpacing(INPUTS_LAYOUT_HSPACING)
        main_layout.setVerticalSpacing(INPUTS_LAYOUT_VSPACING)
        main_layout.addRow("Variant", variant_input)
        main_layout.addRow("Folder", folder_value_widget)
        main_layout.addRow("Task", task_value_widget)
        main_layout.addRow("Product type", product_type_value_widget)
        main_layout.addRow("Product name", product_value_widget)
        main_layout.addRow(btns_layout)

        variant_input.value_changed.connect(self._on_variant_change)
        folder_value_widget.value_changed.connect(self._on_folder_change)
        task_value_widget.value_changed.connect(self._on_task_change)
        submit_btn.clicked.connect(self._on_submit)
        cancel_btn.clicked.connect(self._on_cancel)

        controller.register_event_callback(
            "create.context.value.changed",
            self._on_instance_value_change
        )

        self.variant_input = variant_input
        self.folder_value_widget = folder_value_widget
        self.task_value_widget = task_value_widget
        self.product_type_value_widget = product_type_value_widget
        self.product_value_widget = product_value_widget
        self.submit_btn = submit_btn
        self.cancel_btn = cancel_btn

    def _on_submit(self):
        """Commit changes for selected instances."""

        variant_value = None
        folder_path = None
        task_name = None
        if self.variant_input.has_value_changed():
            variant_value = self.variant_input.get_value()[0]

        if self.folder_value_widget.has_value_changed():
            folder_path = self.folder_value_widget.get_selected_items()[0]

        if self.task_value_widget.has_value_changed():
            task_name = self.task_value_widget.get_selected_items()[0]

        product_names = set()
        invalid_tasks = False
        folder_paths = []
        changes_by_id = {}
        for item in self._current_instances_by_id.values():
            # Ignore instances that have promised context
            if item.has_promised_context:
                continue

            instance_changes = {}
            new_variant_value = item.variant
            new_folder_path = item.folder_path
            new_task_name = item.task_name
            if variant_value is not None:
                instance_changes["variant"] = variant_value
                new_variant_value = variant_value

            if folder_path is not None:
                instance_changes["folderPath"] = folder_path
                new_folder_path = folder_path

            if task_name is not None:
                instance_changes["task"] = task_name or None
                new_task_name = task_name or None

            folder_paths.append(new_folder_path)
            try:
                new_product_name = self._controller.get_product_name(
                    item.creator_identifier,
                    new_variant_value,
                    new_task_name,
                    new_folder_path,
                    item.id,
                )
                self._invalid_task_item_ids.discard(item.id)

            except TaskNotSetError:
                self._invalid_task_item_ids.add(item.id)
                invalid_tasks = True
                product_names.add(item.product_name)
                continue

            product_names.add(new_product_name)
            if item.product_name != new_product_name:
                instance_changes["productName"] = new_product_name

            if instance_changes:
                changes_by_id[item.id] = instance_changes

        if invalid_tasks:
            self.task_value_widget.set_invalid_empty_task()

        self.product_value_widget.set_value(product_names)

        self._set_btns_enabled(False)
        self._set_btns_visible(invalid_tasks)

        if variant_value is not None:
            self.variant_input.confirm_value()

        if folder_path is not None:
            self.folder_value_widget.confirm_value()

        if task_name is not None:
            self.task_value_widget.confirm_value(folder_paths)

        self._controller.set_instances_context_info(changes_by_id)
        self._refresh_items()

    def _on_cancel(self):
        """Cancel changes and set back to their irigin value."""

        self.variant_input.reset_to_origin()
        self.folder_value_widget.reset_to_origin()
        self.task_value_widget.reset_to_origin()
        self._set_btns_enabled(False)

    def _on_value_change(self):
        any_invalid = (
            not self.variant_input.is_valid()
            or not self.folder_value_widget.is_valid()
            or not self.task_value_widget.is_valid()
        )
        any_changed = (
            self.variant_input.has_value_changed()
            or self.folder_value_widget.has_value_changed()
            or self.task_value_widget.has_value_changed()
        )
        self._set_btns_visible(any_changed or any_invalid)
        self.cancel_btn.setEnabled(any_changed)
        self.submit_btn.setEnabled(not any_invalid)

    def _on_variant_change(self):
        self._on_value_change()

    def _on_folder_change(self):
        folder_paths = self.folder_value_widget.get_selected_items()
        self.task_value_widget.set_folder_paths(folder_paths)
        self._on_value_change()

    def _on_task_change(self):
        self._on_value_change()

    def _set_btns_visible(self, visible):
        self.cancel_btn.setVisible(visible)
        self.submit_btn.setVisible(visible)

    def _set_btns_enabled(self, enabled):
        self.cancel_btn.setEnabled(enabled)
        self.submit_btn.setEnabled(enabled)

    def set_current_instances(self, instances):
        """Set currently selected instances.

        Args:
            instances (List[InstanceItem]): List of selected instances.
                Empty instances tells that nothing or context is selected.
        """
        self._set_btns_visible(False)

        self._current_instances_by_id = {
            instance.id: instance
            for instance in instances
        }
        self._invalid_task_item_ids = set()
        self._refresh_content()

    def _refresh_items(self):
        instance_ids = set(self._current_instances_by_id.keys())
        self._current_instances_by_id = (
            self._controller.get_instance_items_by_id(instance_ids)
        )

    def _refresh_content(self):
        folder_paths = set()
        variants = set()
        product_types = set()
        product_names = set()

        editable = True
        if len(self._current_instances_by_id) == 0:
            editable = False

        folder_task_combinations = []
        context_editable = None
        invalid_tasks = False
        for item in self._current_instances_by_id.values():
            if not item.has_promised_context:
                context_editable = True
            elif context_editable is None:
                context_editable = False
                if item.id in self._invalid_task_item_ids:
                    invalid_tasks = True

            # NOTE I'm not sure how this can even happen?
            if item.creator_identifier is None:
                editable = False

            variants.add(item.variant or self.unknown_value)
            product_types.add(item.product_type or self.unknown_value)
            folder_path = item.folder_path or self.unknown_value
            task_name = item.task_name or ""
            folder_paths.add(folder_path)
            folder_task_combinations.append((folder_path, task_name))
            product_names.add(item.product_name or self.unknown_value)

        if not editable:
            context_editable = False
        elif context_editable is None:
            context_editable = True

        self.variant_input.set_value(variants)

        # Set context of folder widget
        self.folder_value_widget.set_selected_items(folder_paths)
        # Set context of task widget
        self.task_value_widget.set_selected_items(folder_task_combinations)
        self.product_type_value_widget.set_value(product_types)
        self.product_value_widget.set_value(product_names)

        self.variant_input.setEnabled(editable)
        self.folder_value_widget.setEnabled(context_editable)
        self.task_value_widget.setEnabled(context_editable)

        if invalid_tasks:
            self.task_value_widget.set_invalid_empty_task()

        if not editable:
            folder_tooltip = "Select instances to change folder path."
            task_tooltip = "Select instances to change task name."
        elif not context_editable:
            folder_tooltip = "Folder path is defined by Create plugin."
            task_tooltip = "Task is defined by Create plugin."
        else:
            folder_tooltip = "Change folder path of selected instances."
            task_tooltip = "Change task of selected instances."

        self.folder_value_widget.setToolTip(folder_tooltip)
        self.task_value_widget.setToolTip(task_tooltip)

    def _on_instance_value_change(self, event):
        if not self._current_instances_by_id:
            return

        changed = False
        for instance_id, changes in event["instance_changes"].items():
            if instance_id not in self._current_instances_by_id:
                continue

            for key in (
                "folderPath",
                "task",
                "variant",
                "productType",
                "productName",
            ):
                if key in changes:
                    changed = True
                    break
            if changed:
                break

        if changed:
            self._refresh_items()
            self._refresh_content()
