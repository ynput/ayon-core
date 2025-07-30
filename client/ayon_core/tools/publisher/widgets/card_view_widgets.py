# -*- coding: utf-8 -*-
"""Card view instance with more information about each instance.

Instances are grouped under groups. Groups are defined by `creator_label`
attribute on instance (Group defined by creator).

Only one item can be selected at a time.

```
<i> : Icon. Can have Warning icon when context is not right
┌──────────────────────┐
│  Context             │
│ <Group 1> ────────── │
│ <i> <Instance 1>  [x]│
│ <i> <Instance 2>  [x]│
│ <Group 2> ────────── │
│ <i> <Instance 3>  [x]│
│ ...                  │
└──────────────────────┘
```
"""
from __future__ import annotations

import re
import collections
from typing import Optional

from qtpy import QtWidgets, QtCore

from ayon_core.pipeline.create import (
    InstanceContextInfo,
    ParentFlags,
)

from ayon_core.tools.utils import BaseClickableFrame, NiceCheckbox
from ayon_core.tools.utils.lib import html_escape
from ayon_core.tools.publisher.abstract import AbstractPublisherFrontend
from ayon_core.tools.publisher.constants import (
    CONTEXT_ID,
    CONTEXT_LABEL,
    CONTEXT_GROUP,
    CONVERTOR_ITEM_GROUP,
)
from ayon_core.tools.publisher.models.create import (
    InstanceItem,
)
from .widgets import (
    AbstractInstanceView,
    ContextWarningLabel,
    IconValuePixmapLabel,
    PublishPixmapLabel
)


class SelectionTypes:
    clear = "clear"
    extend = "extend"
    extend_to = "extend_to"


class BaseGroupWidget(QtWidgets.QWidget):
    selected = QtCore.Signal(str, str, str)
    removed_selected = QtCore.Signal()
    double_clicked = QtCore.Signal()

    def __init__(self, group_name, parent):
        super().__init__(parent)

        label_widget = QtWidgets.QLabel(group_name, self)

        line_widget = QtWidgets.QWidget(self)
        line_widget.setObjectName("Separator")
        line_widget.setMinimumHeight(2)
        line_widget.setMaximumHeight(2)

        label_layout = QtWidgets.QHBoxLayout()
        label_layout.setAlignment(QtCore.Qt.AlignVCenter)
        label_layout.setSpacing(10)
        label_layout.setContentsMargins(0, 0, 0, 0)
        label_layout.addWidget(label_widget, 0)
        label_layout.addWidget(line_widget, 1)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(label_layout, 0)

        self._group = group_name

        self._widgets_by_id = {}

        self._label_widget = label_widget
        self._content_layout = layout

    @property
    def group_name(self):
        """Group which widget represent.

        Returns:
            str: Name of group.
        """

        return self._group

    def set_widgets(
        self,
        widgets_by_id: dict[str, QtWidgets.QWidget],
        ordered_ids: list[str],
    ) -> None:
        self._remove_all_except(set(self._widgets_by_id))
        idx = 1
        for item_id in ordered_ids:
            widget = widgets_by_id[item_id]
            self._content_layout.insertWidget(idx, widget)
            self._widgets_by_id[item_id] = widget
            idx += 1

    def take_widgets(self, widget_ids: set[str]):
        for widget_id in widget_ids:
            widget = self._widgets_by_id.pop(widget_id)
            index = self._content_layout.indexOf(widget)
            if index >= 0:
                self._content_layout.takeAt(index)

    def _remove_all_except(self, item_ids):
        item_ids = set(item_ids)
        # Remove instance widgets that are not in passed instances
        for item_id in tuple(self._widgets_by_id.keys()):
            if item_id in item_ids:
                continue

            widget = self._widgets_by_id.pop(item_id)
            if widget.is_selected:
                self.removed_selected.emit()

            widget.setVisible(False)
            self._content_layout.removeWidget(widget)
            widget.deleteLater()


class CardWidget(BaseClickableFrame):
    """Clickable card used as bigger button."""

    selected = QtCore.Signal(str, str, str)
    # Group identifier of card
    # - this must be set because if send when mouse is released with card id
    _group_identifier = None
    double_clicked = QtCore.Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("CardViewWidget")

        self._selected = False
        self._id = None

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        if self._is_valid_double_click(event):
            self.double_clicked.emit()

    @property
    def id(self):
        """Id of card."""

        return self._id

    @property
    def is_selected(self):
        """Is card selected."""
        return self._selected

    def set_selected(self, selected):
        """Set card as selected."""
        if selected is self._selected:
            return

        self._selected = selected
        state = "selected" if selected else ""
        self.setProperty("state", state)
        self.style().polish(self)

    def _mouse_release_callback(self):
        """Trigger selected signal."""

        modifiers = QtWidgets.QApplication.keyboardModifiers()
        selection_type = SelectionTypes.clear
        if bool(modifiers & QtCore.Qt.ShiftModifier):
            selection_type = SelectionTypes.extend_to

        elif bool(modifiers & QtCore.Qt.ControlModifier):
            selection_type = SelectionTypes.extend

        self.selected.emit(self._id, self._group_identifier, selection_type)

    def _is_valid_double_click(self, event):
        return True


class ContextCardWidget(CardWidget):
    """Card for global context.

    Is not visually under group widget and is always at the top of card view.
    """

    def __init__(self, parent):
        super().__init__(parent)

        self._id = CONTEXT_ID
        self._group_identifier = CONTEXT_GROUP

        icon_widget = PublishPixmapLabel(None, self)
        icon_widget.setObjectName("ProductTypeIconLabel")

        label_widget = QtWidgets.QLabel(CONTEXT_LABEL, self)

        icon_layout = QtWidgets.QHBoxLayout()
        icon_layout.setContentsMargins(5, 5, 5, 5)
        icon_layout.addWidget(icon_widget)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 10, 2)
        layout.addLayout(icon_layout, 0)
        layout.addWidget(label_widget, 1)

        self._icon_widget = icon_widget
        self._label_widget = label_widget


class ConvertorItemCardWidget(CardWidget):
    """Card for global context.

    Is not visually under group widget and is always at the top of card view.
    """

    def __init__(self, item, parent):
        super().__init__(parent)

        self._id = item.id
        self.identifier = item.identifier
        self._group_identifier = CONVERTOR_ITEM_GROUP

        icon_widget = IconValuePixmapLabel("fa.magic", self)
        icon_widget.setObjectName("ProductTypeIconLabel")

        label_widget = QtWidgets.QLabel(item.label, self)

        icon_layout = QtWidgets.QHBoxLayout()
        icon_layout.setContentsMargins(10, 5, 5, 5)
        icon_layout.addWidget(icon_widget)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 10, 2)
        layout.addLayout(icon_layout, 0)
        layout.addWidget(label_widget, 1)

        self._icon_widget = icon_widget
        self._label_widget = label_widget

    def update_item(self, item):
        self._id = item.id
        self.identifier = item.identifier


class InstanceCardWidget(CardWidget):
    """Card widget representing instance."""

    active_changed = QtCore.Signal(str, bool)

    def __init__(
        self,
        instance,
        context_info,
        is_parent_active: bool,
        group_icon,
        parent: BaseGroupWidget,
    ):
        super().__init__(parent)

        self.instance = instance
        self._is_active = instance.is_active

        self._id = instance.id
        self._group_identifier = instance.group_label
        self._group_icon = group_icon
        self._is_parent_active = is_parent_active
        self._toggle_is_enabled = True

        self._last_product_name = None
        self._last_variant = None
        self._last_label = None

        icon_widget = IconValuePixmapLabel(group_icon, self)
        icon_widget.setObjectName("ProductTypeIconLabel")
        context_warning = ContextWarningLabel(self)

        icon_layout = QtWidgets.QHBoxLayout()
        icon_layout.setContentsMargins(10, 5, 5, 5)
        icon_layout.addWidget(icon_widget)
        icon_layout.addWidget(context_warning)

        label_widget = QtWidgets.QLabel(self)
        active_checkbox = NiceCheckbox(parent=self)

        expand_btn = QtWidgets.QToolButton(self)
        # Not yet implemented
        expand_btn.setVisible(False)
        expand_btn.setObjectName("ArrowBtn")
        expand_btn.setArrowType(QtCore.Qt.DownArrow)
        expand_btn.setMaximumWidth(14)
        expand_btn.setEnabled(False)

        detail_widget = QtWidgets.QWidget(self)
        detail_widget.setVisible(False)
        self.detail_widget = detail_widget

        top_layout = QtWidgets.QHBoxLayout()
        top_layout.addLayout(icon_layout, 0)
        top_layout.addWidget(label_widget, 1)
        top_layout.addWidget(context_warning, 0)
        top_layout.addWidget(active_checkbox, 0)
        top_layout.addWidget(expand_btn, 0)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 10, 2)
        layout.addLayout(top_layout)
        layout.addWidget(detail_widget)

        active_checkbox.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        expand_btn.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        active_checkbox.stateChanged.connect(self._on_active_change)
        expand_btn.clicked.connect(self._on_expend_clicked)

        self._icon_widget = icon_widget
        self._label_widget = label_widget
        self._context_warning = context_warning
        self._active_checkbox = active_checkbox
        self._expand_btn = expand_btn

        self._update_instance_values(context_info, is_parent_active)

    def set_active_toggle_enabled(self, enabled: bool) -> None:
        if self._toggle_is_enabled is enabled:
            return
        self._toggle_is_enabled = enabled
        self._update_checkbox_state()

    def is_active(self) -> bool:
        return self._active_checkbox.isChecked()

    def set_active(self, active: Optional[bool]) -> None:
        if not self.is_checkbox_enabled():
            return
        if active is None:
            active = not self.is_active()
        self._set_checked(active)

    def is_parent_active(self) -> bool:
        return self._is_parent_active

    def set_parent_active(self, is_active: bool) -> None:
        if self._is_parent_active is is_active:
            return
        self._is_parent_active = is_active
        self._update_checkbox_state()

    def is_checkbox_enabled(self) -> bool:
        """Checkbox can be changed by user."""
        return (
            self._used_parent_active()
            and not self.instance.is_mandatory
        )

    def update_instance(self, instance, context_info, is_parent_active):
        """Update instance object and update UI."""
        self.instance = instance
        self._is_active = instance.is_active
        self._update_instance_values(context_info, is_parent_active)

    def _validate_context(self, context_info):
        valid = context_info.is_valid
        self._icon_widget.setVisible(valid)
        self._context_warning.setVisible(not valid)

    def _update_product_name(self):
        variant = self.instance.variant
        product_name = self.instance.product_name
        label = self.instance.label

        if (
            variant == self._last_variant
            and product_name == self._last_product_name
            and label == self._last_label
        ):
            return

        self._last_variant = variant
        self._last_product_name = product_name
        self._last_label = label
        # Make `variant` bold
        label = html_escape(self.instance.label)
        found_parts = set(re.findall(variant, label, re.IGNORECASE))
        if found_parts:
            for part in found_parts:
                replacement = "<b>{}</b>".format(part)
                label = label.replace(part, replacement)

        self._label_widget.setText(label)
        # HTML text will cause that label start catch mouse clicks
        # - disabling with changing interaction flag
        self._label_widget.setTextInteractionFlags(
            QtCore.Qt.NoTextInteraction
        )

    def _update_instance_values(self, context_info, is_parent_active):
        """Update instance data"""
        self._is_parent_active = is_parent_active
        self._update_product_name()
        self._update_checkbox_state()
        self._validate_context(context_info)

    def _update_checkbox_state(self):
        parent_is_enabled = self._used_parent_active()
        self._label_widget.setEnabled(parent_is_enabled)
        self._active_checkbox.setEnabled(
            self._toggle_is_enabled
            and not self.instance.is_mandatory
            and parent_is_enabled
        )
        # Hide checkbox for mandatory instances
        self._active_checkbox.setVisible(not self.instance.is_mandatory)

        # Visually disable instance if parent is disabled
        checked = parent_is_enabled and self._is_active
        self._set_checked(checked)

    def _set_checked(self, checked: bool) -> None:
        if checked is not self._active_checkbox.isChecked():
            self._active_checkbox.blockSignals(True)
            self._active_checkbox.setChecked(checked)
            self._active_checkbox.blockSignals(False)

    def _used_parent_active(self) -> bool:
        parent_enabled = True
        if self.instance.parent_flags & ParentFlags.share_active:
            parent_enabled = self._is_parent_active
        return parent_enabled

    def _set_expanded(self, expanded=None):
        if expanded is None:
            expanded = not self.detail_widget.isVisible()
        self.detail_widget.setVisible(expanded)

    def _on_active_change(self):
        new_value = self._active_checkbox.isChecked()
        old_value = self._is_active
        if new_value is old_value:
            return
        self._is_active = new_value
        self.active_changed.emit(self._id, new_value)

    def _on_expend_clicked(self):
        self._set_expanded()

    def _is_valid_double_click(self, event):
        widget = self.childAt(event.pos())
        if (
            widget is self._active_checkbox
            or widget is self._expand_btn
        ):
            return False
        return True


class InstanceCardView(AbstractInstanceView):
    """Publish access to card view.

    Wrapper of all widgets in card view.
    """

    double_clicked = QtCore.Signal()

    def __init__(self, controller, parent):
        super().__init__(parent)

        self._controller: AbstractPublisherFrontend = controller

        scroll_area = QtWidgets.QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scrollbar_bg = scroll_area.verticalScrollBar().parent()
        if scrollbar_bg:
            scrollbar_bg.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        scroll_area.setViewportMargins(0, 0, 0, 0)

        content_widget = QtWidgets.QWidget(scroll_area)

        scroll_area.setWidget(content_widget)

        content_layout = QtWidgets.QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addStretch(1)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll_area)

        self._scroll_area = scroll_area
        self._content_layout = content_layout
        self._content_widget = content_widget

        self._active_toggle_enabled: bool = True
        self._convertors_group: Optional[BaseGroupWidget] = None
        self._convertor_widgets_by_id: dict[str, ConvertorItemCardWidget] = {}
        self._convertor_ids: list[str] = []

        self._group_name_by_instance_id: dict[str, str] = {}
        self._instance_ids_by_group_name: dict[str, list[str]] = (
            collections.defaultdict(list)
        )
        self._ordered_groups = []
        self._group_icons = {}
        self._context_widget: Optional[ContextCardWidget] = None
        self._widgets_by_id: dict[str, InstanceCardWidget] = {}
        self._widgets_by_group: dict[str, BaseGroupWidget] = {}

        self._instance_ids_by_parent_id = collections.defaultdict(set)

        self._explicitly_selected_instance_ids = []
        self._explicitly_selected_groups = []

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Minimum,
            self.sizePolicy().verticalPolicy()
        )

    def sizeHint(self):
        """Modify sizeHint based on visibility of scroll bars."""
        # Calculate width hint by content widget and vertical scroll bar
        scroll_bar = self._scroll_area.verticalScrollBar()
        width = (
            self._content_widget.sizeHint().width()
            + scroll_bar.sizeHint().width()
        )

        result = super().sizeHint()
        result.setWidth(width)
        return result

    def _toggle_instances(
        self,
        new_value: Optional[bool],
        active_id: Optional[str] = None,
    ) -> None:
        instance_ids = {
            widget.id
            for widget in self._get_selected_instance_widgets()
            if widget.is_selected
        }
        active_by_id = {}
        if active_id and active_id not in instance_ids:
            instance_ids = {active_id}

        affected_ids = set(instance_ids)
        _queue = collections.deque()
        _queue.append((set(self._instance_ids_by_parent_id[None]), True))
        discarted_ids = set()
        while _queue:
            if not instance_ids:
                break

            chilren_ids, is_parent_active = _queue.pop()
            for instance_id in chilren_ids:
                widget = self._widgets_by_id[instance_id]
                add_children = False
                if instance_id in affected_ids:
                    affected_ids.discard(instance_id)
                    instance_ids.discard(instance_id)
                    discarted_ids.add(instance_id)
                    add_children = True
                    value = new_value
                    if value is None:
                        value = not widget.is_active()
                    old_value = widget.is_active()
                    widget.set_active(value)
                    if old_value is not widget.is_active():
                        active_by_id[instance_id] = value

                if (
                    instance_id in instance_ids
                    and is_parent_active is not widget.is_parent_active()
                ):
                    add_children = True
                    widget.set_parent_active(is_parent_active)

                    instance_ids.discard(instance_id)
                    discarted_ids.add(instance_id)

                if not add_children:
                    continue

                children_ids = self._instance_ids_by_parent_id[instance_id]
                children = {
                    child_id
                    for child_id in children_ids
                    if child_id not in discarted_ids
                }

                if children:
                    instance_ids |= children
                    _queue.append((children, widget.is_active()))

                if not instance_ids:
                    break

        self._controller.set_instances_active_state(active_by_id)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Space:
            self._toggle_instances(None)
            return True

        elif event.key() == QtCore.Qt.Key_Backspace:
            self._toggle_instances(False)
            return True

        elif event.key() == QtCore.Qt.Key_Return:
            self._toggle_instances(True)
            return True

        return super().keyPressEvent(event)

    def _get_selected_widgets(self):
        output = []
        if (
            self._context_widget is not None
            and self._context_widget.is_selected
        ):
            output.append(self._context_widget)

        output.extend(
            widget
            for widget in self._convertor_widgets_by_id.values()
            if widget.is_selected
        )

        output.extend(self._get_selected_instance_widgets())
        return output

    def _get_selected_instance_widgets(self) -> list[InstanceCardWidget]:
        return [
            widget
            for widget in self._widgets_by_id.values()
            if widget.is_selected
        ]

    def _get_selected_item_ids(self):
        output = []
        if (
            self._context_widget is not None
            and self._context_widget.is_selected
        ):
            output.append(CONTEXT_ID)

        output.extend(
            conv_id
            for conv_id, widget in self._widgets_by_id.items()
            if widget.is_selected
        )

        output.extend(
            widget.id
            for instance_id, widget in self._widgets_by_id.items()
            if widget.is_selected
        )
        return output

    def refresh(self):
        """Refresh instances in view based on CreatedContext."""

        self._make_sure_context_widget_exists()

        self._update_convertors_group()

        context_info_by_id = self._controller.get_instances_context_info()

        # Prepare instances by group and identifiers by group
        instances_by_group = collections.defaultdict(list)
        identifiers_by_group = collections.defaultdict(set)
        identifiers: set[str] = set()
        instances_by_id = {}
        instance_ids_by_parent_id = collections.defaultdict(set)
        instance_items = self._controller.get_instance_items()
        for instance in instance_items:
            group_name = instance.group_label
            instances_by_group[group_name].append(instance)
            identifiers_by_group[group_name].add(
                instance.creator_identifier
            )
            identifiers.add(instance.creator_identifier)
            instances_by_id[instance.id] = instance
            instance_ids_by_parent_id[instance.parent_instance_id].add(
                instance.id
            )

        parent_active_by_id = {
            instance_id: False
            for instance_id in instances_by_id
        }
        _queue = collections.deque()
        _queue.append((None, True))
        while _queue:
            parent_id, is_parent_active = _queue.popleft()
            for instance_id in instance_ids_by_parent_id[parent_id]:
                instance_item = instances_by_id[instance_id]
                is_active = instance_item.is_active
                if (
                    not is_parent_active
                    and instance_item.parent_flags & ParentFlags.share_active
                ):
                    is_active = False

                parent_active_by_id[instance_id] = is_parent_active
                _queue.append(
                    (instance_id, is_active)
                )

        # Remove groups that were not found in passed instances
        groups_to_remove = (
            set(self._widgets_by_group) - set(instances_by_group)
        )

        # Sort groups
        sorted_group_names = list(sorted(instances_by_group.keys()))

        # Keep track of widget indexes
        # - we start with 1 because Context item as at the top
        widget_idx = 1
        if self._convertors_group is not None:
            widget_idx += 1

        group_by_instance_id = {}
        instance_ids_by_group_name = collections.defaultdict(list)
        group_icons = {
            identifier: self._controller.get_creator_icon(identifier)
            for identifier in identifiers
        }
        for group_name in sorted_group_names:
            if group_name not in self._widgets_by_group:
                group_widget = BaseGroupWidget(
                    group_name, self._content_widget
                )
                group_widget.double_clicked.connect(self.double_clicked)
                self._content_layout.insertWidget(widget_idx, group_widget)
                self._widgets_by_group[group_name] = group_widget

            widget_idx += 1

            instances = instances_by_group[group_name]
            for instance in instances:
                group_by_instance_id[instance.id] = group_name
                instance_ids_by_group_name[group_name].append(instance.id)

            self._update_instance_widgets(
                group_name,
                instances,
                context_info_by_id,
                parent_active_by_id,
                group_icons,
            )

        # Remove empty groups
        for group_name in groups_to_remove:
            widget = self._widgets_by_group.pop(group_name)
            widget.setVisible(False)
            self._content_layout.removeWidget(widget)
            widget.deleteLater()

            if group_name in self._explicitly_selected_groups:
                self._explicitly_selected_groups.remove(group_name)

        self._instance_ids_by_parent_id = instance_ids_by_parent_id
        self._group_name_by_instance_id = group_by_instance_id
        self._instance_ids_by_group_name = instance_ids_by_group_name 
        self._ordered_groups = sorted_group_names

    def has_items(self) -> bool:
        if self._convertors_group is not None:
            return True
        if self._widgets_by_id:
            return True
        return False

    def _update_instance_widgets(
        self,
        group_name: str,
        instances: list[InstanceItem],
        context_info_by_id: dict[str, InstanceContextInfo],
        parent_active_by_id: dict[str, bool],
        group_icons: dict[str, str],
    ) -> None:
        """Update instances for the group.

        Args:
            instances (list[InstanceItem]): List of instances in
                CreateContext.
            context_info_by_id (dict[str, InstanceContextInfo]): Instance
                context info by instance id.
            parent_active_by_id (dict[str, bool]): Instance has active parent.

        """
        # Store instances by id and by product name
        group_widget: BaseGroupWidget = self._widgets_by_group[group_name]
        instances_by_id = {}
        instances_by_product_name = collections.defaultdict(list)
        for instance in instances:
            instances_by_id[instance.id] = instance
            product_name = instance.product_name
            instances_by_product_name[product_name].append(instance)

        to_remove_ids = set(
            self._instance_ids_by_group_name[group_name]
        ) - set(instances_by_id)
        group_widget.take_widgets(to_remove_ids)

        # Sort instances by product name
        sorted_product_names = list(sorted(instances_by_product_name.keys()))

        # Add new instances to widget
        ordered_ids = []
        widgets_by_id = {}
        for product_names in sorted_product_names:
            for instance in instances_by_product_name[product_names]:
                context_info = context_info_by_id[instance.id]
                is_parent_active = parent_active_by_id[instance.id]
                if instance.id in self._widgets_by_id:
                    widget = self._widgets_by_id[instance.id]
                    widget.update_instance(
                        instance, context_info, is_parent_active
                    )
                else:
                    group_icon = group_icons[instance.creator_identifier]
                    widget = InstanceCardWidget(
                        instance,
                        context_info,
                        is_parent_active,
                        group_icon,
                        group_widget
                    )
                    widget.selected.connect(self._on_widget_selection)
                    widget.active_changed.connect(self._on_active_changed)
                    widget.double_clicked.connect(self.double_clicked)
                    self._widgets_by_id[instance.id] = widget

                ordered_ids.append(instance.id)
                widgets_by_id[instance.id] = widget

        group_widget.set_widgets(widgets_by_id, ordered_ids)

    def _make_sure_context_widget_exists(self):
        # Create context item if is not already existing
        # - this must be as first thing to do as context item should be at the
        #   top
        if self._context_widget is not None:
            return

        widget = ContextCardWidget(self._content_widget)
        widget.selected.connect(self._on_widget_selection)
        widget.double_clicked.connect(self.double_clicked)

        self._context_widget = widget

        self.selection_changed.emit()
        self._content_layout.insertWidget(0, widget)

    def _update_convertors_group(self):
        convertor_items = self._controller.get_convertor_items()
        if not convertor_items and self._convertors_group is None:
            return

        ids_to_remove = set(self._convertor_widgets_by_id) - set(
            convertor_items
        )
        if ids_to_remove:
            self._convertors_group.take_widgets(ids_to_remove)

        for conv_id in ids_to_remove:
            widget = self._convertor_widgets_by_id.pop(conv_id)
            widget.setVisible(False)
            widget.deleteLater()

        if not convertor_items:
            self._convertors_group.setVisible(False)
            self._content_layout.removeWidget(self._convertors_group)
            self._convertors_group.deleteLater()
            self._convertors_group = None
            self._convertor_ids = []
            self._convertor_widgets_by_id = {}
            return

        if self._convertors_group is None:
            group_widget = BaseGroupWidget(
                CONVERTOR_ITEM_GROUP, self._content_widget
            )
            self._content_layout.insertWidget(1, group_widget)
            self._convertors_group = group_widget

        # TODO create convertor widgets
        items_by_label = collections.defaultdict(list)
        for item in convertor_items.values():
            items_by_label[item.label].append(item)

        # Sort instances by product name
        sorted_labels = list(sorted(items_by_label.keys()))

        # Add new instances to widget
        convertor_ids: list[str] = []
        widgets_by_id: dict[str, ConvertorItemCardWidget] = {}
        for label in sorted_labels:
            for item in items_by_label[label]:
                convertor_ids.append(item.id)
                if item.id in self._convertor_widgets_by_id:
                    widget = self._convertor_widgets_by_id[item.id]
                    widget.update_item(item)
                else:
                    widget = ConvertorItemCardWidget(item, self)
                    widget.selected.connect(self._on_widget_selection)
                    widget.double_clicked.connect(self.double_clicked)
                    self._convertor_widgets_by_id[item.id] = widget
                widgets_by_id[item.id] = widget

        self._convertors_group.set_widgets(widgets_by_id, convertor_ids)
        self._convertor_ids = convertor_ids
        self._convertor_widgets_by_id = widgets_by_id

    def refresh_instance_states(self, instance_ids=None):
        """Trigger update of instances on group widgets."""
        if instance_ids is not None:
            instance_ids = set(instance_ids)
        context_info_by_id = self._controller.get_instances_context_info()
        instance_items_by_id = self._controller.get_instance_items_by_id(
            instance_ids
        )
        instance_ids: set[str] = set(instance_items_by_id)
        available_ids: set[str] = set(instance_items_by_id)
        discarted_ids: set[str] = set()

        _queue = collections.deque()
        _queue.append((set(self._instance_ids_by_parent_id[None]), True))
        while _queue:
            if not instance_ids:
                break

            chilren_ids, is_parent_active = _queue.pop()
            for instance_id in chilren_ids:
                widget = self._widgets_by_id[instance_id]
                add_children = False
                if instance_id in instance_ids:
                    add_children = (
                        is_parent_active is not widget.is_parent_active()
                    )
                    if instance_id in available_ids:
                        available_ids.discard(instance_id)
                        widget.update_instance(
                            instance_items_by_id[instance_id],
                            context_info_by_id[instance_id],
                            is_parent_active,
                        )
                    else:
                        widget.set_parent_active(is_parent_active)

                    instance_ids.discard(instance_id)
                    discarted_ids.add(instance_id)

                if not add_children:
                    continue

                children_ids = self._instance_ids_by_parent_id[instance_id]
                children = {
                    child_id
                    for child_id in children_ids
                    if child_id not in discarted_ids
                }

                if children:
                    instance_ids |= children
                    _queue.append((children, widget.is_active()))

                if not instance_ids:
                    break

    def _on_active_changed(self, instance_id: str, value: bool) -> None:
        self._toggle_instances(value, instance_id)

    def _on_widget_selection(self, instance_id, group_name, selection_type):
        """Select specific item by instance id.

        Pass `CONTEXT_ID` as instance id and empty string as group to select
        global context item.
        """
        if instance_id == CONTEXT_ID:
            new_widget = self._context_widget

        else:
            if group_name == CONVERTOR_ITEM_GROUP:
                new_widget = self._convertor_widgets_by_id[instance_id]
            else:
                new_widget = self._widgets_by_id[instance_id]

        if selection_type == SelectionTypes.clear:
            self._select_item_clear(instance_id, group_name, new_widget)
        elif selection_type == SelectionTypes.extend:
            self._select_item_extend(instance_id, group_name, new_widget)
        elif selection_type == SelectionTypes.extend_to:
            self._select_item_extend_to(instance_id, group_name, new_widget)

        self.selection_changed.emit()

    def _select_item_clear(self, instance_id, group_name, new_widget):
        """Select specific item by instance id and clear previous selection.

        Pass `CONTEXT_ID` as instance id and empty string as group to select
        global context item.
        """

        selected_widgets = self._get_selected_widgets()
        for widget in selected_widgets:
            if widget.id != instance_id:
                widget.set_selected(False)

        self._explicitly_selected_groups = [group_name]
        self._explicitly_selected_instance_ids = [instance_id]

        if new_widget is not None:
            new_widget.set_selected(True)

    def _select_item_extend(self, instance_id, group_name, new_widget):
        """Add/Remove single item to/from current selection.

        If item is already selected the selection is removed.
        """

        self._explicitly_selected_instance_ids = (
            self._get_selected_item_ids()
        )
        if new_widget.is_selected:
            self._explicitly_selected_instance_ids.remove(instance_id)
            new_widget.set_selected(False)
            remove_group = False
            if instance_id == CONTEXT_ID:
                remove_group = True
            else:
                has_selected_items = False
                if group_name == CONVERTOR_ITEM_GROUP:
                    for widget in self._convertor_widgets_by_id.values():
                        if widget.is_selected:
                            has_selected_items = True
                            break
                else:
                    group_ids = self._instance_ids_by_group_name[group_name]
                    for instance_id in group_ids:
                        widget = self._widgets_by_id[instance_id]
                        if widget.is_selected:
                            has_selected_items = True
                            break

                if not has_selected_items:
                    remove_group = True

            if remove_group:
                self._explicitly_selected_groups.remove(group_name)
            return

        self._explicitly_selected_instance_ids.append(instance_id)
        if group_name in self._explicitly_selected_groups:
            self._explicitly_selected_groups.remove(group_name)
        self._explicitly_selected_groups.append(group_name)
        new_widget.set_selected(True)

    def _select_item_extend_to(self, instance_id, group_name, new_widget):
        """Extend selected items to specific instance id.

        This method is handling Shift+click selection of widgets. Selection
        is not stored to explicit selection items. That's because user can
        shift select again and it should use last explicit selected item as
        source item for selection.

        Items selected via this function can get to explicit selection only if
        selection is extended by one specific item ('_select_item_extend').
        From that moment the selection is locked to new last explicit selected
        item.

        It's required to traverse through group widgets in their UI order and
        through their instances in UI order. All explicitly selected items
        must not change their selection state during this function. Passed
        instance id can be above or under last selected item so a start item
        and end item must be found to be able know which direction is selection
        happening.
        """

        # Start group name (in '_ordered_groups')
        start_group = None
        # End group name (in '_ordered_groups')
        end_group = None
        # Instance id of first selected item
        start_instance_id = None
        # Instance id of last selected item
        end_instance_id = None

        # Get previously selected group by explicit selected groups
        previous_group = None
        if self._explicitly_selected_groups:
            previous_group = self._explicitly_selected_groups[-1]

        # Find last explicitly selected instance id
        previous_last_selected_id = None
        if self._explicitly_selected_instance_ids:
            previous_last_selected_id = (
                self._explicitly_selected_instance_ids[-1]
            )

        # If last instance id was not found or available then last selected
        #   group is also invalid.
        # NOTE: This probably never happen?
        if previous_last_selected_id is None:
            previous_group = None

        # Check if previously selected group is available and find out if
        #   new instance group is above or under previous selection
        # - based on these information are start/end group/instance filled
        if previous_group in self._ordered_groups:
            new_idx = self._ordered_groups.index(group_name)
            prev_idx = self._ordered_groups.index(previous_group)
            if new_idx < prev_idx:
                start_group = group_name
                end_group = previous_group
                start_instance_id = instance_id
                end_instance_id = previous_last_selected_id
            else:
                start_group = previous_group
                end_group = group_name
                start_instance_id = previous_last_selected_id
                end_instance_id = instance_id

        # If start group is not set then use context item group name
        if start_group is None:
            start_group = CONTEXT_GROUP

        # If start instance id is not filled then use context id (similar to
        #   group)
        if start_instance_id is None:
            start_instance_id = CONTEXT_ID

        # If end group is not defined then use passed group name
        #   - this can be happen when previous group was not selected
        #   - when this happens the selection will probably happen from context
        #       item to item selected by user
        if end_group is None:
            end_group = group_name

        # If end instance is not filled then use instance selected by user
        if end_instance_id is None:
            end_instance_id = instance_id

        # Start and end group are the same
        # - a different logic is needed in that case
        same_group = start_group == end_group

        # Process known information and change selection of items
        passed_start_group = False
        passed_end_group = False
        # Go through ordered groups (from top to bottom) and change selection
        for name in self._ordered_groups:
            # Prepare sorted instance widgets
            if name == CONTEXT_GROUP:
                sorted_widgets = [self._context_widget]
            else:
                if name == CONVERTOR_ITEM_GROUP:
                    sorted_widgets = [
                        self._convertor_widgets_by_id[conv_id]
                        for conv_id in self._convertor_ids
                    ]
                else:
                    instance_ids = self._instance_ids_by_group_name[name]
                    sorted_widgets = [
                        self._widgets_by_id[instance_id]
                        for instance_id in instance_ids
                    ]

            # Change selection based on explicit selection if start group
            #   was not passed yet
            if not passed_start_group:
                if name != start_group:
                    for widget in sorted_widgets:
                        widget.set_selected(
                            widget.id in self._explicitly_selected_instance_ids
                        )
                    continue

            # Change selection based on explicit selection if end group
            #   already passed
            if passed_end_group:
                for widget in sorted_widgets:
                    widget.set_selected(
                        widget.id in self._explicitly_selected_instance_ids
                    )
                continue

            # Start group is already passed and end group was not yet hit
            if same_group:
                passed_start_group = True
                passed_end_group = True
                passed_start_instance = False
                passed_end_instance = False
                for widget in sorted_widgets:
                    if not passed_start_instance:
                        if widget.id in (start_instance_id, end_instance_id):
                            if widget.id != start_instance_id:
                                # Swap start/end instance if start instance is
                                #   after end
                                # - fix 'passed_end_instance' check
                                start_instance_id, end_instance_id = (
                                    end_instance_id, start_instance_id
                                )
                            passed_start_instance = True

                    # Find out if widget should be selected
                    select = False
                    if passed_end_instance:
                        select = False

                    elif passed_start_instance:
                        select = True

                    # Check if instance is in explicitly selected items if
                    #   should ont be selected
                    if (
                        not select
                        and widget.id in self._explicitly_selected_instance_ids
                    ):
                        select = True

                    widget.set_selected(select)

                    if (
                        not passed_end_instance
                        and widget.id == end_instance_id
                    ):
                        passed_end_instance = True

            elif name == start_group:
                # First group from which selection should start
                # - look for start instance first from which the selection
                #   should happen
                passed_start_group = True
                passed_start_instance = False
                for widget in sorted_widgets:
                    if widget.id == start_instance_id:
                        passed_start_instance = True

                    select = False
                    # Check if passed start instance or instance is
                    #   in explicitly selected items to be selected
                    if (
                        passed_start_instance
                        or widget.id in self._explicitly_selected_instance_ids
                    ):
                        select = True
                    widget.set_selected(select)

            elif name == end_group:
                # Last group where selection should happen
                # - look for end instance first after which the selection
                #   should stop
                passed_end_group = True
                passed_end_instance = False
                for widget in sorted_widgets:
                    select = False
                    # Check if not yet passed end instance or if instance is
                    #   in explicitly selected items to be selected
                    if (
                        not passed_end_instance
                        or widget.id in self._explicitly_selected_instance_ids
                    ):
                        select = True

                    widget.set_selected(select)

                    if widget.id == end_instance_id:
                        passed_end_instance = True

            else:
                # Just select everything between start and end group
                for widget in sorted_widgets:
                    widget.set_selected(True)

    def get_selected_items(self):
        """Get selected instance ids and context."""

        convertor_identifiers = []
        instances = []
        selected_widgets = self._get_selected_widgets()

        context_selected = False
        for widget in selected_widgets:
            if widget is self._context_widget:
                context_selected = True

            elif isinstance(widget, InstanceCardWidget):
                instances.append(widget.id)

            elif isinstance(widget, ConvertorItemCardWidget):
                convertor_identifiers.append(widget.identifier)

        return instances, context_selected, convertor_identifiers

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

        selected_groups = []
        selected_instances = []
        if context_selected:
            selected_groups.append(CONTEXT_GROUP)
            selected_instances.append(CONTEXT_ID)

        self._context_widget.set_selected(context_selected)

        for group_name in self._ordered_groups:
            if group_name == CONTEXT_GROUP:
                continue

            is_convertor_group = group_name == CONVERTOR_ITEM_GROUP
            if is_convertor_group:
                sorted_widgets = [
                    self._convertor_widgets_by_id[conv_id]
                    for conv_id in self._convertor_ids
                ]
            else:
                instance_ids = self._instance_ids_by_group_name[group_name]
                sorted_widgets = [
                    self._widgets_by_id[instance_id]
                    for instance_id in instance_ids
                ]

            group_selected = False
            for widget in sorted_widgets:
                select = False
                if is_convertor_group:
                    is_in = widget.identifier in s_convertor_identifiers
                else:
                    is_in = widget.id in s_instance_ids
                if is_in:
                    selected_instances.append(widget.id)
                    group_selected = True
                    select = True
                widget.set_selected(select)

            if group_selected:
                selected_groups.append(group_name)

        self._explicitly_selected_groups = selected_groups
        self._explicitly_selected_instance_ids = selected_instances

    def set_active_toggle_enabled(self, enabled):
        if self._active_toggle_enabled is enabled:
            return
        self._active_toggle_enabled = enabled
        for widget in self._widgets_by_id.values():
            widget.set_active_toggle_enabled(enabled)
