import typing
from typing import Dict, List, Any

from qtpy import QtWidgets, QtCore

from ayon_core.lib.attribute_definitions import AbstractAttrDef, UnknownDef
from ayon_core.tools.attribute_defs import (
    create_widget_for_attr_def,
    AttributeDefinitionsLabel,
)
from ayon_core.tools.publisher.abstract import AbstractPublisherFrontend
from ayon_core.tools.publisher.constants import (
    INPUTS_LAYOUT_HSPACING,
    INPUTS_LAYOUT_VSPACING,
)

if typing.TYPE_CHECKING:
    from typing import Union


class _CreateAttrDefInfo:
    """Helper class to store information about create attribute definition."""
    def __init__(
        self,
        attr_def: AbstractAttrDef,
        instance_ids: List["Union[str, None]"],
        defaults: List[Any],
        label_widget: "Union[AttributeDefinitionsLabel, None]",
    ):
        self.attr_def: AbstractAttrDef = attr_def
        self.instance_ids: List["Union[str, None]"] = instance_ids
        self.defaults: List[Any] = defaults
        self.label_widget: "Union[AttributeDefinitionsLabel, None]" = (
            label_widget
        )


class _PublishAttrDefInfo:
    """Helper class to store information about publish attribute definition."""
    def __init__(
        self,
        attr_def: AbstractAttrDef,
        plugin_name: str,
        instance_ids: List["Union[str, None]"],
        defaults: List[Any],
        label_widget: "Union[AttributeDefinitionsLabel, None]",
    ):
        self.attr_def: AbstractAttrDef = attr_def
        self.plugin_name: str = plugin_name
        self.instance_ids: List["Union[str, None]"] = instance_ids
        self.defaults: List[Any] = defaults
        self.label_widget: "Union[AttributeDefinitionsLabel, None]" = (
            label_widget
        )


class CreatorAttrsWidget(QtWidgets.QWidget):
    """Widget showing creator specific attributes for selected instances.

    Attributes are defined on creator so are dynamic. Their look and type is
    based on attribute definitions that are defined in
    `~/ayon_core/lib/attribute_definitions.py` and their widget
    representation in `~/ayon_core/tools/attribute_defs/*`.

    Widgets are disabled if context of instance is not valid.

    Definitions are shown for all instance no matter if they are created with
    different creators. If creator have same (similar) definitions their
    widgets are merged into one (different label does not count).
    """

    def __init__(
        self, controller: AbstractPublisherFrontend, parent: QtWidgets.QWidget
    ):
        super().__init__(parent)

        scroll_area = QtWidgets.QScrollArea(self)
        scroll_area.setWidgetResizable(True)

        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(scroll_area, 1)

        controller.register_event_callback(
            "create.context.create.attrs.changed",
            self._on_instance_attr_defs_change
        )
        controller.register_event_callback(
            "create.context.value.changed",
            self._on_instance_value_change
        )

        self._main_layout = main_layout

        self._controller: AbstractPublisherFrontend = controller
        self._scroll_area = scroll_area

        self._attr_def_info_by_id: Dict[str, _CreateAttrDefInfo] = {}
        self._current_instance_ids = set()

        # To store content of scroll area to prevent garbage collection
        self._content_widget = None

    def set_instances_valid(self, valid):
        """Change valid state of current instances."""

        if (
            self._content_widget is not None
            and self._content_widget.isEnabled() != valid
        ):
            self._content_widget.setEnabled(valid)

    def set_current_instances(self, instance_ids):
        """Set current instances for which are attribute definitions shown."""

        self._current_instance_ids = set(instance_ids)
        self._refresh_content()

    def _refresh_content(self):
        prev_content_widget = self._scroll_area.widget()
        if prev_content_widget:
            self._scroll_area.takeWidget()
            prev_content_widget.hide()
            prev_content_widget.deleteLater()

        self._content_widget = None
        self._attr_def_info_by_id = {}

        result = self._controller.get_creator_attribute_definitions(
            self._current_instance_ids
        )

        content_widget = QtWidgets.QWidget(self._scroll_area)
        content_layout = QtWidgets.QGridLayout(content_widget)
        content_layout.setColumnStretch(0, 0)
        content_layout.setColumnStretch(1, 1)
        content_layout.setAlignment(QtCore.Qt.AlignTop)
        content_layout.setHorizontalSpacing(INPUTS_LAYOUT_HSPACING)
        content_layout.setVerticalSpacing(INPUTS_LAYOUT_VSPACING)

        row = 0
        for attr_def, info_by_id in result:
            widget = create_widget_for_attr_def(
                attr_def, content_widget, handle_revert_to_default=False
            )
            default_values = []
            if attr_def.is_value_def:
                values = []
                for item in info_by_id.values():
                    values.append(item["value"])
                    # 'set' cannot be used for default values because they can
                    #    be unhashable types, e.g. 'list'.
                    default = item["default"]
                    if default not in default_values:
                        default_values.append(default)

                if len(values) == 1:
                    value = values[0]
                    if value is not None:
                        widget.set_value(values[0])
                else:
                    widget.set_value(values, True)

            widget.value_changed.connect(self._input_value_changed)
            widget.revert_to_default_requested.connect(
                self._on_request_revert_to_default
            )
            attr_def_info = _CreateAttrDefInfo(
                attr_def, list(info_by_id), default_values, None
            )
            self._attr_def_info_by_id[attr_def.id] = attr_def_info

            if not attr_def.visible:
                continue

            expand_cols = 2
            if attr_def.is_value_def and attr_def.is_label_horizontal:
                expand_cols = 1

            col_num = 2 - expand_cols

            label = None
            is_overriden = False
            if attr_def.is_value_def:
                is_overriden = any(
                    item["value"] != item["default"]
                    for item in info_by_id.values()
                )
                label = attr_def.label or attr_def.key

            if label:
                label_widget = AttributeDefinitionsLabel(
                    attr_def.id, label, self
                )
                tooltip = attr_def.tooltip
                if tooltip:
                    label_widget.setToolTip(tooltip)
                if attr_def.is_label_horizontal:
                    label_widget.setAlignment(
                        QtCore.Qt.AlignRight
                        | QtCore.Qt.AlignVCenter
                    )
                content_layout.addWidget(
                    label_widget, row, 0, 1, expand_cols
                )
                if not attr_def.is_label_horizontal:
                    row += 1
                attr_def_info.label_widget = label_widget
                label_widget.set_overridden(is_overriden)
                label_widget.revert_to_default_requested.connect(
                    self._on_request_revert_to_default
                )

            content_layout.addWidget(
                widget, row, col_num, 1, expand_cols
            )
            row += 1

        self._scroll_area.setWidget(content_widget)
        self._content_widget = content_widget

    def _on_instance_attr_defs_change(self, event):
        for instance_id in event.data["instance_ids"]:
            if instance_id in self._current_instance_ids:
                self._refresh_content()
                break

    def _on_instance_value_change(self, event):
        # TODO try to find more optimized way to update values instead of
        #     force refresh of all of them.
        for instance_id, changes in event["instance_changes"].items():
            if (
                instance_id in self._current_instance_ids
                and "creator_attributes" in changes
            ):
                self._refresh_content()
                break

    def _input_value_changed(self, value, attr_id):
        attr_def_info = self._attr_def_info_by_id.get(attr_id)
        if attr_def_info is None:
            return

        if attr_def_info.label_widget is not None:
            defaults = attr_def_info.defaults
            is_overriden = len(defaults) != 1 or value not in defaults
            attr_def_info.label_widget.set_overridden(is_overriden)

        self._controller.set_instances_create_attr_values(
            attr_def_info.instance_ids,
            attr_def_info.attr_def.key,
            value
        )

    def _on_request_revert_to_default(self, attr_id):
        attr_def_info = self._attr_def_info_by_id.get(attr_id)
        if attr_def_info is None:
            return
        self._controller.revert_instances_create_attr_values(
            attr_def_info.instance_ids,
            attr_def_info.attr_def.key,
        )
        self._refresh_content()


class PublishPluginAttrsWidget(QtWidgets.QWidget):
    """Widget showing publish plugin attributes for selected instances.

    Attributes are defined on publish plugins. Publish plugin may define
    attribute definitions but must inherit `AYONPyblishPluginMixin`
    (~/ayon_core/pipeline/publish). At the moment requires to implement
    `get_attribute_defs` and `convert_attribute_values` class methods.

    Look and type of attributes is based on attribute definitions that are
    defined in `~/ayon_core/lib/attribute_definitions.py` and their
    widget representation in `~/ayon_core/tools/attribute_defs/*`.

    Widgets are disabled if context of instance is not valid.

    Definitions are shown for all instance no matter if they have different
    product types. Similar definitions are merged into one (different label
    does not count).
    """

    def __init__(
        self, controller: AbstractPublisherFrontend, parent: QtWidgets.QWidget
    ):
        super().__init__(parent)

        scroll_area = QtWidgets.QScrollArea(self)
        scroll_area.setWidgetResizable(True)

        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(scroll_area, 1)

        controller.register_event_callback(
            "create.context.publish.attrs.changed",
            self._on_instance_attr_defs_change
        )
        controller.register_event_callback(
            "create.context.value.changed",
            self._on_instance_value_change
        )

        self._current_instance_ids = set()
        self._context_selected = False

        self._main_layout = main_layout

        self._controller: AbstractPublisherFrontend = controller
        self._scroll_area = scroll_area

        self._attr_def_info_by_id: Dict[str, _PublishAttrDefInfo] = {}

        # Store content of scroll area to prevent garbage collection
        self._content_widget = None

    def set_instances_valid(self, valid):
        """Change valid state of current instances."""
        if (
            self._content_widget is not None
            and self._content_widget.isEnabled() != valid
        ):
            self._content_widget.setEnabled(valid)

    def set_current_instances(self, instance_ids, context_selected):
        """Set current instances for which are attribute definitions shown."""

        self._current_instance_ids = set(instance_ids)
        self._context_selected = context_selected
        self._refresh_content()

    def _refresh_content(self):
        prev_content_widget = self._scroll_area.widget()
        if prev_content_widget:
            self._scroll_area.takeWidget()
            prev_content_widget.hide()
            prev_content_widget.deleteLater()

        self._content_widget = None

        self._attr_def_info_by_id = {}

        result = self._controller.get_publish_attribute_definitions(
            self._current_instance_ids, self._context_selected
        )

        content_widget = QtWidgets.QWidget(self._scroll_area)
        attr_def_widget = QtWidgets.QWidget(content_widget)
        attr_def_layout = QtWidgets.QGridLayout(attr_def_widget)
        attr_def_layout.setColumnStretch(0, 0)
        attr_def_layout.setColumnStretch(1, 1)
        attr_def_layout.setHorizontalSpacing(INPUTS_LAYOUT_HSPACING)
        attr_def_layout.setVerticalSpacing(INPUTS_LAYOUT_VSPACING)

        content_layout = QtWidgets.QVBoxLayout(content_widget)
        content_layout.addWidget(attr_def_widget, 0)
        content_layout.addStretch(1)

        row = 0
        for plugin_name, attr_defs, plugin_values in result:
            for attr_def in attr_defs:
                widget = create_widget_for_attr_def(
                    attr_def, content_widget, handle_revert_to_default=False
                )
                visible_widget = attr_def.visible
                # Hide unknown values of publish plugins
                # - The keys in most of the cases does not represent what
                #    would label represent
                if isinstance(attr_def, UnknownDef):
                    widget.setVisible(False)
                    visible_widget = False

                label_widget = None
                if visible_widget:
                    expand_cols = 2
                    if attr_def.is_value_def and attr_def.is_label_horizontal:
                        expand_cols = 1

                    col_num = 2 - expand_cols
                    label = None
                    if attr_def.is_value_def:
                        label = attr_def.label or attr_def.key
                    if label:
                        label_widget = AttributeDefinitionsLabel(
                            attr_def.id, label, content_widget
                        )
                        label_widget.revert_to_default_requested.connect(
                            self._on_request_revert_to_default
                        )
                        tooltip = attr_def.tooltip
                        if tooltip:
                            label_widget.setToolTip(tooltip)
                        if attr_def.is_label_horizontal:
                            label_widget.setAlignment(
                                QtCore.Qt.AlignRight
                                | QtCore.Qt.AlignVCenter
                            )
                        attr_def_layout.addWidget(
                            label_widget, row, 0, 1, expand_cols
                        )
                        if not attr_def.is_label_horizontal:
                            row += 1
                    attr_def_layout.addWidget(
                        widget, row, col_num, 1, expand_cols
                    )
                    row += 1

                if not attr_def.is_value_def:
                    continue

                widget.value_changed.connect(self._input_value_changed)
                widget.revert_to_default_requested.connect(
                    self._on_request_revert_to_default
                )

                instance_ids = []
                values = []
                default_values = []
                is_overriden = False
                for (instance_id, value, default_value) in (
                    plugin_values.get(attr_def.key, [])
                ):
                    instance_ids.append(instance_id)
                    values.append(value)
                    if not is_overriden and value != default_value:
                        is_overriden = True
                    # 'set' cannot be used for default values because they can
                    #    be unhashable types, e.g. 'list'.
                    if default_value not in default_values:
                        default_values.append(default_value)

                multivalue = len(values) > 1

                self._attr_def_info_by_id[attr_def.id] = _PublishAttrDefInfo(
                    attr_def,
                    plugin_name,
                    instance_ids,
                    default_values,
                    label_widget,
                )

                if multivalue:
                    widget.set_value(values, multivalue)
                else:
                    widget.set_value(values[0])

                if label_widget is not None:
                    label_widget.set_overridden(is_overriden)

        self._scroll_area.setWidget(content_widget)
        self._content_widget = content_widget

    def _input_value_changed(self, value, attr_id):
        attr_def_info = self._attr_def_info_by_id.get(attr_id)
        if attr_def_info is None:
            return

        if attr_def_info.label_widget is not None:
            defaults = attr_def_info.defaults
            is_overriden = len(defaults) != 1 or value not in defaults
            attr_def_info.label_widget.set_overridden(is_overriden)

        self._controller.set_instances_publish_attr_values(
            attr_def_info.instance_ids,
            attr_def_info.plugin_name,
            attr_def_info.attr_def.key,
            value
        )

    def _on_request_revert_to_default(self, attr_id):
        attr_def_info = self._attr_def_info_by_id.get(attr_id)
        if attr_def_info is None:
            return

        self._controller.revert_instances_publish_attr_values(
            attr_def_info.instance_ids,
            attr_def_info.plugin_name,
            attr_def_info.attr_def.key,
        )
        self._refresh_content()

    def _on_instance_attr_defs_change(self, event):
        for instance_id in event.data:
            if (
                instance_id is None and self._context_selected
                or instance_id in self._current_instance_ids
            ):
                self._refresh_content()
                break

    def _on_instance_value_change(self, event):
        # TODO try to find more optimized way to update values instead of
        #     force refresh of all of them.
        for instance_id, changes in event["instance_changes"].items():
            if (
                instance_id in self._current_instance_ids
                and "publish_attributes" in changes
            ):
                self._refresh_content()
                break
