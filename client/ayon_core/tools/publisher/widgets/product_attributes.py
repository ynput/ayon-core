from qtpy import QtWidgets, QtCore

from ayon_core.lib.attribute_definitions import UnknownDef
from ayon_core.tools.attribute_defs import create_widget_for_attr_def
from ayon_core.tools.publisher.abstract import AbstractPublisherFrontend
from ayon_core.tools.publisher.constants import (
    INPUTS_LAYOUT_HSPACING,
    INPUTS_LAYOUT_VSPACING,
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

        self._attr_def_id_to_instances = {}
        self._attr_def_id_to_attr_def = {}
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
        self._attr_def_id_to_instances = {}
        self._attr_def_id_to_attr_def = {}

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
        for attr_def, instance_ids, values in result:
            widget = create_widget_for_attr_def(attr_def, content_widget)
            if attr_def.is_value_def:
                if len(values) == 1:
                    value = values[0]
                    if value is not None:
                        widget.set_value(values[0])
                else:
                    widget.set_value(values, True)

            widget.value_changed.connect(self._input_value_changed)
            self._attr_def_id_to_instances[attr_def.id] = instance_ids
            self._attr_def_id_to_attr_def[attr_def.id] = attr_def

            if not attr_def.visible:
                continue

            expand_cols = 2
            if attr_def.is_value_def and attr_def.is_label_horizontal:
                expand_cols = 1

            col_num = 2 - expand_cols

            label = None
            if attr_def.is_value_def:
                label = attr_def.label or attr_def.key
            if label:
                label_widget = QtWidgets.QLabel(label, self)
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
                and "creator_attributes" not in changes
            ):
                self._refresh_content()
                break

    def _input_value_changed(self, value, attr_id):
        instance_ids = self._attr_def_id_to_instances.get(attr_id)
        attr_def = self._attr_def_id_to_attr_def.get(attr_id)
        if not instance_ids or not attr_def:
            return
        self._controller.set_instances_create_attr_values(
            instance_ids, attr_def.key, value
        )


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

        self._attr_def_id_to_instances = {}
        self._attr_def_id_to_attr_def = {}
        self._attr_def_id_to_plugin_name = {}

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

        self._attr_def_id_to_instances = {}
        self._attr_def_id_to_attr_def = {}
        self._attr_def_id_to_plugin_name = {}

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
        for plugin_name, attr_defs, all_plugin_values in result:
            plugin_values = all_plugin_values[plugin_name]

            for attr_def in attr_defs:
                widget = create_widget_for_attr_def(
                    attr_def, content_widget
                )
                visible_widget = attr_def.visible
                # Hide unknown values of publish plugins
                # - The keys in most of the cases does not represent what
                #    would label represent
                if isinstance(attr_def, UnknownDef):
                    widget.setVisible(False)
                    visible_widget = False

                if visible_widget:
                    expand_cols = 2
                    if attr_def.is_value_def and attr_def.is_label_horizontal:
                        expand_cols = 1

                    col_num = 2 - expand_cols
                    label = None
                    if attr_def.is_value_def:
                        label = attr_def.label or attr_def.key
                    if label:
                        label_widget = QtWidgets.QLabel(label, content_widget)
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

                attr_values = plugin_values[attr_def.key]
                multivalue = len(attr_values) > 1
                values = []
                instances = []
                for instance, value in attr_values:
                    values.append(value)
                    instances.append(instance)

                self._attr_def_id_to_attr_def[attr_def.id] = attr_def
                self._attr_def_id_to_instances[attr_def.id] = instances
                self._attr_def_id_to_plugin_name[attr_def.id] = plugin_name

                if multivalue:
                    widget.set_value(values, multivalue)
                else:
                    widget.set_value(values[0])

        self._scroll_area.setWidget(content_widget)
        self._content_widget = content_widget

    def _input_value_changed(self, value, attr_id):
        instance_ids = self._attr_def_id_to_instances.get(attr_id)
        attr_def = self._attr_def_id_to_attr_def.get(attr_id)
        plugin_name = self._attr_def_id_to_plugin_name.get(attr_id)
        if not instance_ids or not attr_def or not plugin_name:
            return

        self._controller.set_instances_publish_attr_values(
            instance_ids, plugin_name, attr_def.key, value
        )

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
                and "publish_attributes" not in changes
            ):
                self._refresh_content()
                break
