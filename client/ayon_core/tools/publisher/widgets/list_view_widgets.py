"""Simple easy instance view grouping instances into collapsible groups.

View has multiselection ability. Groups are defined by `creator_label`
attribute on instance (Group defined by creator).

Each item can be enabled/disabled with their checkbox, whole group
can be enabled/disabled with checkbox on group or
selection can be enabled disabled using checkbox or keyboard key presses:
- Space - change state of selection to opposite
- Enter - enable selection
- Backspace - disable selection

```
|- Context
|- <Group 1> [x]
|  |- <Instance 1> [x]
|  |- <Instance 2> [x]
|  ...
|- <Group 2> [ ]
|  |- <Instance 3> [ ]
|  ...
...
```
"""
from __future__ import annotations

import collections
from typing import Optional

from qtpy import QtWidgets, QtCore, QtGui

from ayon_core.style import get_objected_colors

from ayon_core.pipeline.create import (
    InstanceContextInfo,
    ParentFlags,
)

from ayon_core.tools.utils import NiceCheckbox, BaseClickableFrame
from ayon_core.tools.utils.lib import html_escape, checkstate_int_to_enum
from ayon_core.tools.publisher.abstract import AbstractPublisherFrontend
from ayon_core.tools.publisher.models.create import (
    InstanceItem,
)
from ayon_core.tools.publisher.constants import (
    INSTANCE_ID_ROLE,
    SORT_VALUE_ROLE,
    IS_GROUP_ROLE,
    CONTEXT_ID,
    CONTEXT_LABEL,
    GROUP_ROLE,
    CONVERTER_IDENTIFIER_ROLE,
    CONVERTOR_ITEM_GROUP,
)

from .widgets import AbstractInstanceView


class ListItemDelegate(QtWidgets.QStyledItemDelegate):
    """Generic delegate for instance group.

    All indexes having `IS_GROUP_ROLE` data set to True will use
    `group_item_paint` method to draw it's content otherwise default styled
    item delegate paint method is used.

    Goal is to draw group items with different colors for normal, hover and
    pressed state.
    """
    radius_ratio = 0.3

    def __init__(self, parent):
        super().__init__(parent)

        group_color_info = get_objected_colors("publisher", "list-view-group")

        self._group_colors = {
            key: value.get_qcolor()
            for key, value in group_color_info.items()
        }

    def paint(self, painter, option, index):
        if index.data(IS_GROUP_ROLE):
            self.group_item_paint(painter, option, index)
        else:
            super().paint(painter, option, index)

    def group_item_paint(self, painter, option, index):
        """Paint group item."""
        self.initStyleOption(option, index)

        bg_rect = QtCore.QRectF(
            option.rect.left(), option.rect.top() + 1,
            option.rect.width(), option.rect.height() - 2
        )
        ratio = bg_rect.height() * self.radius_ratio
        bg_path = QtGui.QPainterPath()
        bg_path.addRoundedRect(
            QtCore.QRectF(bg_rect), ratio, ratio
        )

        painter.save()
        painter.setRenderHints(
            QtGui.QPainter.Antialiasing
            | QtGui.QPainter.SmoothPixmapTransform
            | QtGui.QPainter.TextAntialiasing
        )

        # Draw backgrounds
        painter.fillPath(bg_path, self._group_colors["bg"])
        selected = option.state & QtWidgets.QStyle.State_Selected
        hovered = option.state & QtWidgets.QStyle.State_MouseOver
        if selected and hovered:
            painter.fillPath(bg_path, self._group_colors["bg-selected-hover"])

        elif hovered:
            painter.fillPath(bg_path, self._group_colors["bg-hover"])

        painter.restore()


class InstanceListItemWidget(QtWidgets.QWidget):
    """Widget with instance info drawn over delegate paint.

    This is required to be able to use custom checkbox on custom place.
    """
    active_changed = QtCore.Signal(str, bool)
    double_clicked = QtCore.Signal()

    def __init__(
        self,
        instance: InstanceItem,
        context_info: InstanceContextInfo,
        parent_is_active: bool,
        parent: QtWidgets.QWidget,
    ):
        super().__init__(parent)

        self._instance_id = instance.id

        instance_label = instance.label
        if instance_label is None:
            # Do not cause UI crash if label is 'None'
            instance_label = "No label"

        instance_label = html_escape(instance_label)

        product_name_label = QtWidgets.QLabel(instance_label, self)
        product_name_label.setObjectName("ListViewProductName")

        active_checkbox = NiceCheckbox(parent=self)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.addWidget(product_name_label)
        layout.addStretch(1)
        layout.addWidget(active_checkbox)

        for widget in (
            self,
            product_name_label,
            active_checkbox,
        ):
            widget.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        active_checkbox.stateChanged.connect(self._on_active_change)

        self._instance_label_widget = product_name_label
        self._active_checkbox = active_checkbox

        # Instance info
        self._has_valid_context = context_info.is_valid
        self._is_mandatory = instance.is_mandatory
        self._instance_is_active = instance.is_active
        self._parent_flags = instance.parent_flags

        # Parent active state is fluent and can change
        self._parent_is_active = parent_is_active

        # Widget logic info
        self._state = None
        self._toggle_is_enabled = True

        self._update_style_state()
        self._update_checkbox_state()

    def mouseDoubleClickEvent(self, event):
        widget = self.childAt(event.pos())
        super().mouseDoubleClickEvent(event)
        if widget is not self._active_checkbox:
            self.double_clicked.emit()

    def is_active(self) -> bool:
        """Instance is activated."""
        return self._active_checkbox.isChecked()

    def is_checkbox_enabled(self) -> bool:
        """Checkbox can be changed by user."""
        return (
            self._used_parent_active()
            and not self._is_mandatory
        )

    def set_active_toggle_enabled(self, enabled: bool) -> None:
        """Toggle can be available for user."""
        self._toggle_is_enabled = enabled
        self._update_checkbox_state()

    def set_active(self, new_value: Optional[bool]) -> None:
        """Change active state of instance and checkbox by user interaction.

        Args:
            new_value (Optional[bool]): New active state of instance. Toggle
                if is 'None'.

        """
        # Do not allow to change state if is mandatory or parent is not active
        if not self.is_checkbox_enabled():
            return

        if new_value is None:
            new_value = not self._active_checkbox.isChecked()
        # Update instance active state
        self._instance_is_active = new_value
        self._set_checked(new_value)

    def update_instance(
        self,
        instance: InstanceItem,
        context_info: InstanceContextInfo,
        parent_is_active: bool,
    ) -> None:
        """Update instance object."""
        # Check product name
        self._instance_id = instance.id
        label = instance.label
        if label != self._instance_label_widget.text():
            self._instance_label_widget.setText(html_escape(label))

        self._is_mandatory = instance.is_mandatory
        self._instance_is_active = instance.is_active
        self._has_valid_context = context_info.is_valid
        self._parent_is_active = parent_is_active
        self._parent_flags = instance.parent_flags

        self._update_checkbox_state()
        self._update_style_state()

    def is_parent_active(self) -> bool:
        return self._parent_is_active

    def _used_parent_active(self) -> bool:
        parent_enabled = True
        if self._parent_flags & ParentFlags.share_active:
            parent_enabled = self._parent_is_active
        return parent_enabled

    def set_parent_is_active(self, active: bool) -> None:
        if self._parent_is_active is active:
            return
        self._parent_is_active = active
        self._update_style_state()
        self._update_checkbox_state()

    def _set_checked(self, checked: bool) -> None:
        """Change checked state in UI without triggering checkstate change."""
        old_value = self._active_checkbox.isChecked()
        if checked is not old_value:
            self._active_checkbox.blockSignals(True)
            self._active_checkbox.setChecked(checked)
            self._active_checkbox.blockSignals(False)

    def _update_style_state(self) -> None:
        state = ""
        if not self._used_parent_active():
            state = "disabled"
        elif not self._has_valid_context:
            state = "invalid"

        if state == self._state:
            return
        self._state = state
        self._instance_label_widget.setProperty("state", state)
        self._instance_label_widget.style().polish(self._instance_label_widget)

    def _update_checkbox_state(self) -> None:
        parent_enabled = self._used_parent_active()

        self._active_checkbox.setEnabled(
            self._toggle_is_enabled
            and not self._is_mandatory
            and parent_enabled
        )
        # Hide checkbox for mandatory instances
        self._active_checkbox.setVisible(not self._is_mandatory)

        # Visually disable instance if parent is disabled
        checked = parent_enabled and self._instance_is_active
        self._set_checked(checked)

    def _on_active_change(self):
        self.active_changed.emit(
            self._instance_id, self._active_checkbox.isChecked()
        )


class ListContextWidget(QtWidgets.QFrame):
    """Context (or global attributes) widget."""
    double_clicked = QtCore.Signal()

    def __init__(self, parent):
        super().__init__(parent)

        label_widget = QtWidgets.QLabel(CONTEXT_LABEL, self)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(5, 0, 2, 0)
        layout.addWidget(
            label_widget, 1, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
        )

        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        label_widget.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        self.label_widget = label_widget

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        self.double_clicked.emit()


class InstanceListGroupWidget(BaseClickableFrame):
    """Widget representing group of instances.

    Has label of group and checkbox modifying all of its children.
    """
    toggle_requested = QtCore.Signal(str, int)
    expand_change_requested = QtCore.Signal(str)

    def __init__(self, group_name, parent):
        super().__init__(parent)
        self.setObjectName("InstanceListGroupWidget")

        self.group_name = group_name

        name_label = QtWidgets.QLabel(group_name, self)

        toggle_checkbox = NiceCheckbox(parent=self)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.addWidget(
            name_label, 1, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
        )
        layout.addWidget(toggle_checkbox, 0)

        name_label.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        toggle_checkbox.stateChanged.connect(self._on_checkbox_change)

        self._ignore_state_change = False

        self._expected_checkstate = None

        self.name_label = name_label
        self.toggle_checkbox = toggle_checkbox

    def set_checkstate(self, state):
        """Change checkstate of "active" checkbox.

        Args:
            state(QtCore.Qt.CheckState): Checkstate of checkbox. Have 3
                variants Unchecked, Checked and PartiallyChecked.
        """

        if self.checkstate() == state:
            return
        self._ignore_state_change = True
        self.toggle_checkbox.setCheckState(state)
        self._ignore_state_change = False

    def checkstate(self):
        """Current checkstate of "active" checkbox."""

        return self.toggle_checkbox.checkState()

    def set_active_toggle_enabled(self, enabled):
        self.toggle_checkbox.setEnabled(enabled)

    def _on_checkbox_change(self, state):
        if not self._ignore_state_change:
            self.toggle_requested.emit(self.group_name, state)

    def _mouse_release_callback(self):
        self.expand_change_requested.emit(self.group_name)


class InstanceTreeView(QtWidgets.QTreeView):
    """View showing instances and their groups."""
    toggle_requested = QtCore.Signal(int)
    double_clicked = QtCore.Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setObjectName("InstanceListView")
        self.setHeaderHidden(True)
        self.setExpandsOnDoubleClick(False)
        self.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection
        )
        self.viewport().setMouseTracking(True)

    def get_selected_instance_ids(self):
        """Ids of selected instances."""
        instance_ids = set()
        for index in self.selectionModel().selectedIndexes():
            if index.data(CONVERTER_IDENTIFIER_ROLE) is not None:
                continue

            instance_id = index.data(INSTANCE_ID_ROLE)
            if instance_id is not None:
                instance_ids.add(instance_id)
        return instance_ids

    def event(self, event):
        if not event.type() == QtCore.QEvent.KeyPress:
            pass

        elif event.key() == QtCore.Qt.Key_Space:
            self.toggle_requested.emit(-1)
            return True

        elif event.key() == QtCore.Qt.Key_Backspace:
            self.toggle_requested.emit(0)
            return True

        elif event.key() == QtCore.Qt.Key_Return:
            self.toggle_requested.emit(1)
            return True

        return super().event(event)


class InstanceListView(AbstractInstanceView):
    """Widget providing abstract methods of AbstractInstanceView for list view.

    This is public access to and from list view.
    """

    double_clicked = QtCore.Signal()

    def __init__(
        self, controller: AbstractPublisherFrontend, parent: QtWidgets.QWidget
    ):
        super().__init__(parent)

        self._controller: AbstractPublisherFrontend = controller

        instance_view = InstanceTreeView(self)
        instance_delegate = ListItemDelegate(instance_view)
        instance_view.setItemDelegate(instance_delegate)
        instance_model = QtGui.QStandardItemModel()

        proxy_model = QtCore.QSortFilterProxyModel()
        proxy_model.setSourceModel(instance_model)
        proxy_model.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        proxy_model.setSortRole(SORT_VALUE_ROLE)
        proxy_model.setFilterKeyColumn(0)
        proxy_model.setDynamicSortFilter(True)

        instance_view.setModel(proxy_model)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(instance_view)

        instance_view.selectionModel().selectionChanged.connect(
            self._on_selection_change
        )
        instance_view.toggle_requested.connect(self._on_toggle_request)
        instance_view.double_clicked.connect(self.double_clicked)

        self._group_items = {}
        self._group_widgets = {}
        self._widgets_by_id: dict[str, InstanceListItemWidget] = {}
        self._items_by_id = {}
        self._parent_id_by_id = {}
        self._instance_ids_by_parent_id = collections.defaultdict(set)
        # Group by instance id for handling of active state
        self._group_by_instance_id = {}
        self._context_item = None
        self._context_widget = None
        self._missing_parent_item = None
        self._parent_grouping = True

        self._convertor_group_item = None
        self._convertor_group_widget = None
        self._convertor_items_by_id = {}

        self._instance_view = instance_view
        self._instance_delegate = instance_delegate
        self._instance_model = instance_model
        self._proxy_model = proxy_model

        self._active_toggle_enabled = True

    def _on_toggle_request(self, toggle: int) -> None:
        if not self._active_toggle_enabled:
            return

        if toggle == -1:
            active = None
        elif toggle == 1:
            active = True
        else:
            active = False
        self._toggle_active_state(active)

    def _update_group_checkstate(self, group_name):
        """Update checkstate of one group."""
        widget = self._group_widgets.get(group_name)
        if widget is None:
            return

        activity = None
        for (
            instance_id, instance_group_name
        ) in self._group_by_instance_id.items():
            if instance_group_name != group_name:
                continue

            instance_widget = self._widgets_by_id.get(instance_id)
            if not instance_widget:
                continue

            if activity is None:
                activity = int(instance_widget.is_active())

            elif activity != instance_widget.is_active():
                activity = -1
                break

        if activity is None:
            return

        state = QtCore.Qt.PartiallyChecked
        if activity == 0:
            state = QtCore.Qt.Unchecked
        elif activity == 1:
            state = QtCore.Qt.Checked
        widget.set_checkstate(state)

    def refresh(self):
        """Refresh instances in the view."""
        # Sort view at the end of refresh
        # - is turned off until any change in view happens
        sort_at_the_end = False
        # Create or use already existing context item
        # - context widget does not change so we don't have to update anything
        if self._make_sure_context_item_exists():
            sort_at_the_end = True

        self._update_convertor_items_group()

        context_info_by_id = self._controller.get_instances_context_info()
        instance_items = self._controller.get_instance_items()
        # Prepare instances by their groups
        instances_by_group_name = collections.defaultdict(list)
        instances_by_parent_id = collections.defaultdict(list)
        instance_ids_by_parent_id = collections.defaultdict(set)
        group_names = set()
        instance_ids = set()
        for instance in instance_items:
            instance_ids.add(instance.id)
            instance_ids_by_parent_id[instance.parent_instance_id].add(
                instance.id
            )
            if instance.parent_instance_id:
                instances_by_parent_id[instance.parent_instance_id].append(
                    instance
                )
                if self._parent_grouping:
                    continue

            group_label = instance.group_label
            group_names.add(group_label)
            instances_by_group_name[group_label].append(instance)
            self._group_by_instance_id[instance.id] = group_label

        # Create new groups based on prepared `instances_by_group_name`
        if self._make_sure_groups_exists(group_names):
            sort_at_the_end = True

        # Remove groups that are not available anymore
        self._remove_groups_except(group_names)
        self._remove_instances_except(instance_items)

        expand_to_items = []
        widgets_by_id = {}
        group_items = [
            (
                self._group_widgets[group_name],
                instances_by_group_name[group_name],
                group_item,
            )
            for group_name, group_item in self._group_items.items()
        ]

        # Handle orphaned instances
        missing_parent_ids = set(instances_by_parent_id) - instance_ids
        if not missing_parent_ids:
            # Make sure the item is not in view if there are no orhpaned items
            self._remove_missing_parent_item()
        else:
            # Add orphaned group item and append them to 'group_items'
            orphans_item = self._add_missing_parent_item()
            for instance_id in missing_parent_ids:
                group_items.append((
                    None,
                    instances_by_parent_id[instance_id],
                    orphans_item,
                ))

        items_with_instance = {}
        # Process changes in each group item
        # - create new instance, update existing and remove not existing
        for group_widget, group_instances, group_item in group_items:
            # Group widget is not set if is orphaned
            #   - This might need to be changed in future if widget could
            #       be 'None'
            is_orpaned_item = group_widget is None

            # Collect all new instances by parent id
            # - 'None' is used if parent is group item
            new_items = collections.defaultdict(list)
            # Tuples of model item and instance itself
            for instance in group_instances:
                _queue = collections.deque()
                _queue.append((instance, group_item, None))
                while _queue:
                    instance, parent_item, parent_id = _queue.popleft()
                    instance_id = instance.id
                    # Remove group name from groups mapping
                    if parent_id is not None:
                        self._group_by_instance_id.pop(instance_id, None)

                    # Create new item and store it as new
                    item = self._items_by_id.get(instance_id)
                    if item is None:
                        item = QtGui.QStandardItem()
                        item.setData(instance_id, INSTANCE_ID_ROLE)
                        self._items_by_id[instance_id] = item
                        new_items[parent_id].append(item)

                    elif item.parent() is not parent_item:
                        current_parent = item.parent()
                        if current_parent is not None:
                            current_parent.takeRow(item.row())
                        new_items[parent_id].append(item)

                    self._parent_id_by_id[instance_id] = parent_id

                    items_with_instance[instance.id] = (
                        item,
                        instance,
                        is_orpaned_item,
                    )

                    item.setData(instance.product_name, SORT_VALUE_ROLE)
                    item.setData(instance.product_name, GROUP_ROLE)

                    if not self._parent_grouping:
                        continue

                    children = instances_by_parent_id.pop(instance_id, [])
                    for child in children:
                        _queue.append((child, item, instance_id))

            # Process new instance items and add them to model and create
            #   their widgets
            if new_items:
                # Trigger sort at the end when new instances are available
                sort_at_the_end = True

                # Add items under group item
                for parent_id, items in new_items.items():
                    if parent_id is None or not self._parent_grouping:
                        parent_item = group_item
                    else:
                        parent_item = self._items_by_id[parent_id]

                    parent_item.appendRows(items)

        ids_order = []
        ids_queue = collections.deque()
        ids_queue.extend(instance_ids_by_parent_id[None])
        while ids_queue:
            parent_id = ids_queue.popleft()
            ids_order.append(parent_id)
            ids_queue.extend(instance_ids_by_parent_id[parent_id])
        ids_order.extend(set(items_with_instance) - set(ids_order))

        for instance_id in ids_order:
            item, instance, is_orpaned_item = items_with_instance[instance_id]
            context_info = context_info_by_id[instance.id]
            # TODO expand all parents
            if not context_info.is_valid:
                expand_to_items.append(item)

            parent_active = True
            if is_orpaned_item:
                parent_active = False

            parent_id = instance.parent_instance_id
            if parent_id:
                parent_widget = widgets_by_id.get(parent_id)
                parent_active = False
                if parent_widget is not None:
                    parent_active = parent_widget.is_active()
            item_index = self._instance_model.indexFromItem(item)
            proxy_index = self._proxy_model.mapFromSource(item_index)
            widget = self._instance_view.indexWidget(proxy_index)
            if isinstance(widget, InstanceListItemWidget):
                widget.update_instance(
                    instance,
                    context_info,
                    parent_active,
                )
            else:
                widget = InstanceListItemWidget(
                    instance,
                    context_info,
                    parent_active,
                    self._instance_view
                )
                widget.active_changed.connect(self._on_active_changed)
                widget.double_clicked.connect(self.double_clicked)
                self._instance_view.setIndexWidget(proxy_index, widget)
            widget.set_active_toggle_enabled(
                self._active_toggle_enabled
            )

            widgets_by_id[instance.id] = widget
            self._widgets_by_id.pop(instance.id, None)

        for widget in self._widgets_by_id.values():
            widget.setVisible(False)
            widget.deleteLater()

        self._widgets_by_id = widgets_by_id
        self._instance_ids_by_parent_id = instance_ids_by_parent_id

        # Set checkstate of group checkbox
        for group_name in self._group_items:
            self._update_group_checkstate(group_name)

        # Expand items marked for expanding
        items_to_expand = []
        _marked_ids = set()
        for item in expand_to_items:
            parent = item.parent()
            _items = []
            while True:
                # Parent is not set or is group (groups are separate)
                if parent is None or parent.data(IS_GROUP_ROLE):
                    break
                instance_id = parent.data(INSTANCE_ID_ROLE)
                # Parent was already marked for expanding
                if instance_id in _marked_ids:
                    break
                _marked_ids.add(instance_id)
                _items.append(parent)
                parent = parent.parent()

            items_to_expand.extend(reversed(_items))

        for item in items_to_expand:
            proxy_index = self._proxy_model.mapFromSource(item.index())
            self._instance_view.expand(proxy_index)

        # Trigger sort at the end of refresh
        if sort_at_the_end:
            self._proxy_model.sort(0)

    def _make_sure_context_item_exists(self) -> bool:
        if self._context_item is not None:
            return False

        root_item = self._instance_model.invisibleRootItem()
        context_item = QtGui.QStandardItem()
        context_item.setData(0, SORT_VALUE_ROLE)
        context_item.setData(CONTEXT_ID, INSTANCE_ID_ROLE)

        root_item.appendRow(context_item)

        index = self._instance_model.index(
            context_item.row(), context_item.column()
        )
        proxy_index = self._proxy_model.mapFromSource(index)
        widget = ListContextWidget(self._instance_view)
        widget.double_clicked.connect(self.double_clicked)
        self._instance_view.setIndexWidget(proxy_index, widget)

        self._context_widget = widget
        self._context_item = context_item
        return True

    def _update_convertor_items_group(self) -> bool:
        created_new_items = False
        convertor_items_by_id = self._controller.get_convertor_items()
        group_item = self._convertor_group_item
        if not convertor_items_by_id and group_item is None:
            return created_new_items

        root_item = self._instance_model.invisibleRootItem()
        if not convertor_items_by_id:
            root_item.takeRow(group_item.row())
            self._convertor_group_widget.deleteLater()
            self._convertor_group_widget = None
            self._convertor_items_by_id = {}
            return created_new_items

        if group_item is None:
            created_new_items = True
            group_item = QtGui.QStandardItem()
            group_item.setData(CONVERTOR_ITEM_GROUP, GROUP_ROLE)
            group_item.setData(1, SORT_VALUE_ROLE)
            group_item.setData(True, IS_GROUP_ROLE)
            group_item.setFlags(QtCore.Qt.ItemIsEnabled)

            root_item.appendRow(group_item)

            index = self._instance_model.index(
                group_item.row(), group_item.column()
            )
            proxy_index = self._proxy_model.mapFromSource(index)
            widget = InstanceListGroupWidget(
                CONVERTOR_ITEM_GROUP, self._instance_view
            )
            widget.toggle_checkbox.setVisible(False)

            self._instance_view.setIndexWidget(proxy_index, widget)

            self._convertor_group_item = group_item
            self._convertor_group_widget = widget

        for row in reversed(range(group_item.rowCount())):
            child_item = group_item.child(row)
            child_identifier = child_item.data(CONVERTER_IDENTIFIER_ROLE)
            if child_identifier not in convertor_items_by_id:
                self._convertor_items_by_id.pop(child_identifier, None)
                group_item.takeRow(row)

        new_items = []
        for identifier, convertor_item in convertor_items_by_id.items():
            item = self._convertor_items_by_id.get(identifier)
            if item is None:
                created_new_items = True
                item = QtGui.QStandardItem(convertor_item.label)
                new_items.append(item)
            item.setData(convertor_item.id, INSTANCE_ID_ROLE)
            item.setData(convertor_item.label, SORT_VALUE_ROLE)
            item.setData(CONVERTOR_ITEM_GROUP, GROUP_ROLE)
            item.setData(
                convertor_item.identifier, CONVERTER_IDENTIFIER_ROLE
            )
            self._convertor_items_by_id[identifier] = item

        if new_items:
            group_item.appendRows(new_items)

        return created_new_items

    def _make_sure_groups_exists(self, group_names: set[str]) -> bool:
        new_group_items = []
        for group_name in group_names:
            if group_name in self._group_items:
                continue

            group_item = QtGui.QStandardItem()
            group_item.setData(group_name, GROUP_ROLE)
            group_item.setData(group_name, SORT_VALUE_ROLE)
            group_item.setData(True, IS_GROUP_ROLE)
            group_item.setFlags(QtCore.Qt.ItemIsEnabled)
            self._group_items[group_name] = group_item
            new_group_items.append(group_item)

        # Add new group items to root item if there are any
        if not new_group_items:
            return False

        # Access to root item of main model
        root_item = self._instance_model.invisibleRootItem()
        root_item.appendRows(new_group_items)

        # Create widget for each new group item and store it for future usage
        for group_item in new_group_items:
            index = self._instance_model.index(
                group_item.row(), group_item.column()
            )
            proxy_index = self._proxy_model.mapFromSource(index)
            group_name = group_item.data(GROUP_ROLE)
            widget = InstanceListGroupWidget(group_name, self._instance_view)
            widget.set_active_toggle_enabled(
                self._active_toggle_enabled
            )
            widget.toggle_requested.connect(self._on_group_toggle_request)
            widget.expand_change_requested.connect(
                self._on_expand_toggle_request
            )
            self._group_widgets[group_name] = widget
            self._instance_view.setIndexWidget(proxy_index, widget)

        return True

    def _remove_groups_except(self, group_names: set[str]) -> None:
        # Remove groups that are not available anymore
        root_item = self._instance_model.invisibleRootItem()
        for group_name in tuple(self._group_items.keys()):
            if group_name in group_names:
                continue

            group_item = self._group_items.pop(group_name)
            root_item.takeRow(group_item.row())
            widget = self._group_widgets.pop(group_name)
            widget.setVisible(False)
            widget.deleteLater()

    def _remove_instances_except(self, instance_items: list[InstanceItem]):
        parent_id_by_id = {
            item.id: item.parent_instance_id
            for item in instance_items
        }
        instance_ids = set(parent_id_by_id)
        all_removed_ids = set(self._items_by_id) - instance_ids
        queue = collections.deque()
        for group_item in self._group_items.values():
            queue.append((group_item, None))
        while queue:
            parent_item, parent_id = queue.popleft()
            children = [
                parent_item.child(row)
                for row in range(parent_item.rowCount())
            ]
            for child in children:
                instance_id = child.data(INSTANCE_ID_ROLE)
                if instance_id not in parent_id_by_id:
                    parent_item.takeRow(child.row())
                elif parent_id != parent_id_by_id[instance_id]:
                    parent_item.takeRow(child.row())

                queue.append((child, instance_id))

        for instance_id in all_removed_ids:
            self._items_by_id.pop(instance_id)
            self._parent_id_by_id.pop(instance_id)
            self._group_by_instance_id.pop(instance_id, None)
            widget = self._widgets_by_id.pop(instance_id, None)
            if widget is not None:
                widget.setVisible(False)
                widget.deleteLater()

    def _add_missing_parent_item(self) -> QtGui.QStandardItem:
        label = "! Orphaned instances !"
        if self._missing_parent_item is None:
            item = QtGui.QStandardItem()
            item.setData(label, GROUP_ROLE)
            item.setData("_", SORT_VALUE_ROLE)
            item.setData(True, IS_GROUP_ROLE)
            item.setFlags(QtCore.Qt.ItemIsEnabled)
            self._missing_parent_item = item

        if self._missing_parent_item.row() < 0:
            root_item = self._instance_model.invisibleRootItem()
            root_item.appendRow(self._missing_parent_item)
            index = self._missing_parent_item.index()
            proxy_index = self._proxy_model.mapFromSource(index)
            widget = InstanceListGroupWidget(label, self._instance_view)
            widget.toggle_checkbox.setVisible(False)
            self._instance_view.setIndexWidget(proxy_index, widget)
        return self._missing_parent_item

    def _remove_missing_parent_item(self) -> None:
        if self._missing_parent_item is None:
            return

        row = self._missing_parent_item.row()
        if row < 0:
            return

        parent = self._missing_parent_item.parent()
        if parent is None:
            parent = self._instance_model.invisibleRootItem()
        index = self._missing_parent_item.index()
        proxy_index = self._proxy_model.mapFromSource(index)
        widget = self._instance_view.indexWidget(proxy_index)
        if widget is not None:
            widget.setVisible(False)
            widget.deleteLater()
        parent.takeRow(self._missing_parent_item.row())
        _queue = collections.deque()
        _queue.append(self._missing_parent_item)
        while _queue:
            item = _queue.popleft()
            for _ in range(item.rowCount()):
                child = item.child(0)
                _queue.append(child)
                item.takeRow(0)

        self._missing_parent_item = None

    def refresh_instance_states(self, instance_ids=None):
        """Trigger update of all instances."""
        if instance_ids is not None:
            instance_ids = set(instance_ids)

        context_info_by_id = self._controller.get_instances_context_info(
            instance_ids
        )
        instance_items_by_id = self._controller.get_instance_items_by_id(
            instance_ids
        )
        instance_ids = set(instance_items_by_id)
        available_ids = set(instance_ids)

        _queue = collections.deque()
        _queue.append((set(self._instance_ids_by_parent_id[None]), True))

        discarted_ids = set()
        while _queue:
            if not instance_ids:
                break

            children_ids, parent_active = _queue.popleft()
            for instance_id in children_ids:
                widget = self._widgets_by_id[instance_id]
                # Parent active state changed -> traverse children too
                add_children = False                  
                if instance_id in instance_ids:
                    add_children = (
                        parent_active is not widget.is_parent_active()
                    )
                    if instance_id in available_ids:
                        available_ids.discard(instance_id)
                        widget.update_instance(
                            instance_items_by_id[instance_id],
                            context_info_by_id[instance_id],
                            parent_active,
                        )

                    instance_ids.discard(instance_id)
                    discarted_ids.add(instance_id)

                if parent_active is not widget.is_parent_active():
                    widget.set_parent_is_active(parent_active)
                    add_children = True

                if not add_children:
                    if not instance_ids:
                        break
                    continue

                _children = set(self._instance_ids_by_parent_id[instance_id])
                if _children:
                    instance_ids |= _children
                    _queue.append((_children, widget.is_active()))

                if not instance_ids:
                    break

    def parent_grouping_enabled(self) -> bool:
        return self._parent_grouping

    def set_parent_grouping(self, parent_grouping: bool) -> None:
        self._parent_grouping = parent_grouping

    def _on_active_changed(self, changed_instance_id, new_value):
        self._toggle_active_state(new_value, changed_instance_id)

    def _toggle_active_state(
        self,
        new_value: Optional[bool],
        active_id: Optional[str] = None,
        instance_ids: Optional[set[str]] = None,
    ) -> None:
        if instance_ids is None:
            instance_ids, _, _ = self.get_selected_items()
        if active_id and active_id not in instance_ids:
            instance_ids = {active_id}

        active_by_id = {}
        _queue = collections.deque()
        _queue.append((set(self._instance_ids_by_parent_id[None]), True))

        while _queue:
            children_ids, parent_active = _queue.popleft()
            for instance_id in children_ids:
                widget = self._widgets_by_id[instance_id]
                widget.set_parent_is_active(parent_active)
                if instance_id in instance_ids:
                    value = new_value
                    if value is None:
                        value = not widget.is_active()
                    widget.set_active(value)
                    active_by_id[instance_id] = value

                children = set(
                    self._instance_ids_by_parent_id[instance_id]
                )
                if children:
                    _queue.append((children, widget.is_active()))

        self._controller.set_instances_active_state(active_by_id)

        group_names = set()
        for instance_id in active_by_id:
            group_name = self._group_by_instance_id.get(instance_id)
            if group_name is not None:
                group_names.add(group_name)

        for group_name in group_names:
            self._update_group_checkstate(group_name)

    def _on_selection_change(self, *_args):
        self.selection_changed.emit()

    def _on_expand_toggle_request(self, group_name):
        group_item = self._group_items.get(group_name)
        if not group_item:
            return
        proxy_index = self._proxy_model.mapFromSource(group_item.index())
        new_state = not self._instance_view.isExpanded(proxy_index)
        self._instance_view.setExpanded(proxy_index, new_state)

    def _on_group_toggle_request(self, group_name, state):
        state = checkstate_int_to_enum(state)
        if state == QtCore.Qt.PartiallyChecked:
            return

        group_item = self._group_items.get(group_name)
        if not group_item:
            return

        active = state == QtCore.Qt.Checked

        instance_ids = set()
        for row in range(group_item.rowCount()):
            child = group_item.child(row)
            instance_id = child.data(INSTANCE_ID_ROLE)
            instance_ids.add(instance_id)

        self._toggle_active_state(active, instance_ids=instance_ids)

        proxy_index = self._proxy_model.mapFromSource(group_item.index())
        if not self._instance_view.isExpanded(proxy_index):
            self._instance_view.expand(proxy_index)

    def has_items(self) -> bool:
        if self._convertor_group_widget is not None:
            return True
        if self._group_items:
            return True
        return False

    def get_selected_items(self) -> tuple[list[str], bool, list[str]]:
        """Get selected instance ids and context selection.

        Returns:
            tuple[list[str], bool, list[str]]: Selected instance ids,
                boolean if context is selected and selected convertor ids.

        """
        instance_ids = []
        convertor_identifiers = []
        context_selected = False

        for index in self._instance_view.selectionModel().selectedIndexes():
            convertor_identifier = index.data(CONVERTER_IDENTIFIER_ROLE)
            if convertor_identifier is not None:
                convertor_identifiers.append(convertor_identifier)
                continue

            instance_id = index.data(INSTANCE_ID_ROLE)
            if not context_selected and instance_id == CONTEXT_ID:
                context_selected = True

            elif instance_id is not None:
                instance_ids.append(instance_id)

        return instance_ids, context_selected, convertor_identifiers

    def set_selected_items(
        self, instance_ids, context_selected, convertor_identifiers
    ):
        s_instance_ids = set(instance_ids)
        s_convertor_identifiers = set(convertor_identifiers)
        cur_ids, cur_context, cur_convertor_identifiers = (
            self.get_selected_items()
        )
        if (
            set(cur_ids) == s_instance_ids
            and cur_context == context_selected
            and set(cur_convertor_identifiers) == s_convertor_identifiers
        ):
            return

        view = self._instance_view
        src_model = self._instance_model
        proxy_model = self._proxy_model

        select_indexes = []

        select_queue = collections.deque()
        select_queue.append(
            (src_model.invisibleRootItem(), [])
        )
        while select_queue:
            queue_item = select_queue.popleft()
            item, parent_items = queue_item

            if item.hasChildren():
                new_parent_items = list(parent_items)
                new_parent_items.append(item)
                for row in range(item.rowCount()):
                    select_queue.append(
                        (item.child(row), list(new_parent_items))
                    )

            convertor_identifier = item.data(CONVERTER_IDENTIFIER_ROLE)

            select = False
            expand_parent = True
            if convertor_identifier is not None:
                if convertor_identifier in s_convertor_identifiers:
                    select = True
            else:
                instance_id = item.data(INSTANCE_ID_ROLE)
                if instance_id == CONTEXT_ID:
                    if context_selected:
                        select = True
                        expand_parent = False

                elif instance_id in s_instance_ids:
                    select = True

            if not select:
                continue

            select_indexes.append(item.index())
            if not expand_parent:
                continue

            for parent_item in parent_items:
                index = parent_item.index()
                proxy_index = proxy_model.mapFromSource(index)
                if not view.isExpanded(proxy_index):
                    view.expand(proxy_index)

        selection_model = view.selectionModel()
        if not select_indexes:
            selection_model.clear()
            return

        if len(select_indexes) == 1:
            proxy_index = proxy_model.mapFromSource(select_indexes[0])
            selection_model.setCurrentIndex(
                proxy_index,
                QtCore.QItemSelectionModel.ClearAndSelect
                | QtCore.QItemSelectionModel.Rows
            )
            return

        first_index = proxy_model.mapFromSource(select_indexes.pop(0))
        last_index = proxy_model.mapFromSource(select_indexes.pop(-1))

        selection_model.setCurrentIndex(
            first_index,
            QtCore.QItemSelectionModel.ClearAndSelect
            | QtCore.QItemSelectionModel.Rows
        )

        for index in select_indexes:
            proxy_index = proxy_model.mapFromSource(index)
            selection_model.select(
                proxy_index,
                QtCore.QItemSelectionModel.Select
                | QtCore.QItemSelectionModel.Rows
            )

        selection_model.setCurrentIndex(
            last_index,
            QtCore.QItemSelectionModel.Select
            | QtCore.QItemSelectionModel.Rows
        )

    def set_active_toggle_enabled(self, enabled: bool) -> None:
        if self._active_toggle_enabled is enabled:
            return

        self._active_toggle_enabled = enabled
        for widget in self._widgets_by_id.values():
            if isinstance(widget, InstanceListItemWidget):
                widget.set_active_toggle_enabled(enabled)

        for widget in self._group_widgets.values():
            if isinstance(widget, InstanceListGroupWidget):
                widget.set_active_toggle_enabled(enabled)
