import os
import uuid
import shutil

from qtpy import QtWidgets, QtCore

from ayon_core.tools.publisher.abstract import AbstractPublisherFrontend

from .thumbnail_widget import ThumbnailWidget
from .product_context import GlobalAttrsWidget
from .product_attributes import (
    CreatorAttrsWidget,
    PublishPluginAttrsWidget,
)


class ProductInfoWidget(QtWidgets.QWidget):
    """Wrapper widget where attributes of instance/s are modified.
    ┌─────────────────┬─────────────┐
    │   Global        │             │
    │   attributes    │  Thumbnail  │  TOP
    │                 │             │
    ├─────────────┬───┴─────────────┤
    │  Creator    │   Publish       │
    │  attributes │   plugin        │  BOTTOM
    │             │   attributes    │
    └───────────────────────────────┘
    """
    convert_requested = QtCore.Signal()

    def __init__(
        self, controller: AbstractPublisherFrontend, parent: QtWidgets.QWidget
    ):
        super().__init__(parent)

        # TOP PART
        top_widget = QtWidgets.QWidget(self)

        # Global attributes
        global_attrs_widget = GlobalAttrsWidget(controller, top_widget)
        thumbnail_widget = ThumbnailWidget(controller, top_widget)

        top_layout = QtWidgets.QHBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(global_attrs_widget, 7)
        top_layout.addWidget(thumbnail_widget, 3)

        # BOTTOM PART
        bottom_widget = QtWidgets.QWidget(self)

        # Wrap Creator attributes to widget to be able add convert button
        creator_widget = QtWidgets.QWidget(bottom_widget)

        # Convert button widget (with layout to handle stretch)
        convert_widget = QtWidgets.QWidget(creator_widget)
        convert_label = QtWidgets.QLabel(creator_widget)
        # Set the label text with 'setText' to apply html
        convert_label.setText(
            (
                "Found old publishable products"
                " incompatible with new publisher."
                "<br/><br/>Press the <b>update products</b> button"
                " to automatically update them"
                " to be able to publish again."
            )
        )
        convert_label.setWordWrap(True)
        convert_label.setAlignment(QtCore.Qt.AlignCenter)

        convert_btn = QtWidgets.QPushButton(
            "Update products", convert_widget
        )
        convert_separator = QtWidgets.QFrame(convert_widget)
        convert_separator.setObjectName("Separator")
        convert_separator.setMinimumHeight(1)
        convert_separator.setMaximumHeight(1)

        convert_layout = QtWidgets.QGridLayout(convert_widget)
        convert_layout.setContentsMargins(5, 0, 5, 0)
        convert_layout.setVerticalSpacing(10)
        convert_layout.addWidget(convert_label, 0, 0, 1, 3)
        convert_layout.addWidget(convert_btn, 1, 1)
        convert_layout.addWidget(convert_separator, 2, 0, 1, 3)
        convert_layout.setColumnStretch(0, 1)
        convert_layout.setColumnStretch(1, 0)
        convert_layout.setColumnStretch(2, 1)

        # Creator attributes widget
        creator_attrs_widget = CreatorAttrsWidget(
            controller, creator_widget
        )
        creator_layout = QtWidgets.QVBoxLayout(creator_widget)
        creator_layout.setContentsMargins(0, 0, 0, 0)
        creator_layout.addWidget(convert_widget, 0)
        creator_layout.addWidget(creator_attrs_widget, 1)

        publish_attrs_widget = PublishPluginAttrsWidget(
            controller, bottom_widget
        )

        bottom_separator = QtWidgets.QWidget(bottom_widget)
        bottom_separator.setObjectName("Separator")
        bottom_separator.setMinimumWidth(1)

        bottom_layout = QtWidgets.QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.addWidget(creator_widget, 1)
        bottom_layout.addWidget(bottom_separator, 0)
        bottom_layout.addWidget(publish_attrs_widget, 1)

        top_bottom = QtWidgets.QWidget(self)
        top_bottom.setObjectName("Separator")
        top_bottom.setMinimumHeight(1)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(top_widget, 0)
        layout.addWidget(top_bottom, 0)
        layout.addWidget(bottom_widget, 1)

        self._convertor_identifiers = None
        self._current_instances = []
        self._context_selected = False
        self._all_instances_valid = True

        convert_btn.clicked.connect(self._on_convert_click)
        thumbnail_widget.thumbnail_created.connect(self._on_thumbnail_create)
        thumbnail_widget.thumbnail_cleared.connect(self._on_thumbnail_clear)

        controller.register_event_callback(
            "create.model.instances.context.changed",
            self._on_instance_context_change
        )
        controller.register_event_callback(
            "instance.thumbnail.changed",
            self._on_thumbnail_changed
        )

        self._controller: AbstractPublisherFrontend = controller

        self._convert_widget = convert_widget

        self.global_attrs_widget = global_attrs_widget

        self.creator_attrs_widget = creator_attrs_widget
        self.publish_attrs_widget = publish_attrs_widget
        self._thumbnail_widget = thumbnail_widget

        self.top_bottom = top_bottom
        self.bottom_separator = bottom_separator

    def set_current_instances(
        self, instances, context_selected, convertor_identifiers
    ):
        """Change currently selected items.

        Args:
            instances (List[InstanceItem]): List of currently selected
                instances.
            context_selected (bool): Is context selected.
            convertor_identifiers (List[str]): Identifiers of convert items.

        """
        s_convertor_identifiers = set(convertor_identifiers)
        self._current_instances = instances
        self._context_selected = context_selected
        self._convertor_identifiers = s_convertor_identifiers
        self._refresh_instances()

    def _refresh_instances(self):
        instance_ids = {
            instance.id
            for instance in self._current_instances
        }
        context_info_by_id = self._controller.get_instances_context_info(
            instance_ids
        )

        all_valid = True
        for context_info in context_info_by_id.values():
            if not context_info.is_valid:
                all_valid = False
                break

        self._all_instances_valid = all_valid

        self._convert_widget.setVisible(len(self._convertor_identifiers) > 0)
        self.global_attrs_widget.set_current_instances(
            self._current_instances
        )
        self.creator_attrs_widget.set_current_instances(instance_ids)
        self.publish_attrs_widget.set_current_instances(
            instance_ids, self._context_selected
        )
        self.creator_attrs_widget.set_instances_valid(all_valid)
        self.publish_attrs_widget.set_instances_valid(all_valid)

        self._update_thumbnails()

    def _on_instance_context_change(self):
        instance_ids = {
            instance.id
            for instance in self._current_instances
        }
        context_info_by_id = self._controller.get_instances_context_info(
            instance_ids
        )
        all_valid = True
        for instance_id, context_info in context_info_by_id.items():
            if not context_info.is_valid:
                all_valid = False
                break

        self._all_instances_valid = all_valid
        self.creator_attrs_widget.set_instances_valid(all_valid)
        self.publish_attrs_widget.set_instances_valid(all_valid)

    def _on_convert_click(self):
        self.convert_requested.emit()

    def _on_thumbnail_create(self, path):
        instance_ids = [
            instance.id
            for instance in self._current_instances
        ]
        if self._context_selected:
            instance_ids.append(None)

        if not instance_ids:
            return

        mapping = {}
        if len(instance_ids) == 1:
            mapping[instance_ids[0]] = path

        else:
            for instance_id in instance_ids:
                root = os.path.dirname(path)
                ext = os.path.splitext(path)[-1]
                dst_path = os.path.join(root, str(uuid.uuid4()) + ext)
                shutil.copy(path, dst_path)
                mapping[instance_id] = dst_path

        self._controller.set_thumbnail_paths_for_instances(mapping)

    def _on_thumbnail_clear(self):
        instance_ids = [
            instance.id
            for instance in self._current_instances
        ]
        if self._context_selected:
            instance_ids.append(None)

        if not instance_ids:
            return

        mapping = {
            instance_id: None
            for instance_id in instance_ids
        }
        self._controller.set_thumbnail_paths_for_instances(mapping)

    def _on_thumbnail_changed(self, event):
        self._update_thumbnails()

    def _update_thumbnails(self):
        instance_ids = [
            instance.id
            for instance in self._current_instances
        ]
        if self._context_selected:
            instance_ids.append(None)

        if not instance_ids:
            self._thumbnail_widget.setVisible(False)
            self._thumbnail_widget.set_current_thumbnails(None)
            return

        mapping = self._controller.get_thumbnail_paths_for_instances(
            instance_ids
        )
        thumbnail_paths = []
        for instance_id in instance_ids:
            path = mapping[instance_id]
            if path:
                thumbnail_paths.append(path)

        self._thumbnail_widget.setVisible(True)
        self._thumbnail_widget.set_current_thumbnails(thumbnail_paths)
