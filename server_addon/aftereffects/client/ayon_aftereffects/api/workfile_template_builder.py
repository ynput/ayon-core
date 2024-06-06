import os.path
import uuid
import shutil
from abc import abstractmethod

from ayon_core.pipeline import registered_host
from ayon_core.tools.workfile_template_build import (
    WorkfileBuildPlaceholderDialog,
)
from ayon_core.pipeline.workfile.workfile_template_builder import (
    AbstractTemplateBuilder,
    PlaceholderPlugin,
    PlaceholderItem
)
from ayon_aftereffects.api import get_stub

PLACEHOLDER_SET = "PLACEHOLDERS_SET"
PLACEHOLDER_ID = "openpype.placeholder"


class AETemplateBuilder(AbstractTemplateBuilder):
    """Concrete implementation of AbstractTemplateBuilder for AE"""

    def import_template(self, path):
        """Import template into current scene.
        Block if a template is already loaded.

        Args:
            path (str): A path to current template (usually given by
            get_template_preset implementation)

        Returns:
            bool: Whether the template was successfully imported or not
        """
        stub = get_stub()
        if not os.path.exists(path):
            stub.print_msg(f"Template file on {path} doesn't exist.")
            return

        stub.save()
        workfile_path = stub.get_active_document_full_name()
        shutil.copy2(path, workfile_path)
        stub.open(workfile_path)

        return True


class AEPlaceholderPlugin(PlaceholderPlugin):
    """Contains generic methods for all PlaceholderPlugins."""

    @abstractmethod
    def _create_placeholder_item(self, item_data: dict) -> PlaceholderItem:
        pass

    def collect_placeholders(self):
        """Collect info from file metadata about created placeholders.

        Returns:
            (list) (LoadPlaceholderItem)
        """
        output = []
        scene_placeholders = self._collect_scene_placeholders()
        for item in scene_placeholders:
            if item.get("plugin_identifier") != self.identifier:
                continue

            item = self._create_placeholder_item(item)
            output.append(item)

        return output

    def update_placeholder(self, placeholder_item, placeholder_data):
        """Resave changed properties for placeholders"""
        item_id, metadata_item = self._get_item(placeholder_item)
        stub = get_stub()
        if not item_id:
            stub.print_msg("Cannot find item for "
                           f"{placeholder_item.scene_identifier}")
            return
        metadata_item["data"] = placeholder_data
        stub.imprint(item_id, metadata_item)

    def _get_item(self, placeholder_item):
        """Returns item id and item metadata for placeholder from file meta"""
        stub = get_stub()
        placeholder_uuid = placeholder_item.scene_identifier
        for metadata_item in stub.get_metadata():
            if not metadata_item.get("is_placeholder"):
                continue
            if placeholder_uuid in metadata_item.get("uuid"):
                return metadata_item["members"][0], metadata_item
        return None, None

    def _collect_scene_placeholders(self):
        """" Cache placeholder data to shared data.
        Returns:
            (list) of dicts
        """
        placeholder_items = self.builder.get_shared_populate_data(
            "placeholder_items"
        )
        if not placeholder_items:
            placeholder_items = []
            for item in get_stub().get_metadata():
                if not item.get("is_placeholder"):
                    continue
                placeholder_items.append(item)

            self.builder.set_shared_populate_data(
                "placeholder_items", placeholder_items
            )
        return placeholder_items

    def _imprint_item(self, item_id, name, placeholder_data, stub):
        if not item_id:
            raise ValueError("Couldn't create a placeholder")
        container_data = {
            "id": "openpype.placeholder",
            "name": name,
            "is_placeholder": True,
            "plugin_identifier": self.identifier,
            "uuid": str(uuid.uuid4()),  # scene_identifier
            "data": placeholder_data,
            "members": [item_id]
        }
        stub.imprint(item_id, container_data)


def build_workfile_template(*args, **kwargs):
    builder = AETemplateBuilder(registered_host())
    builder.build_template(*args, **kwargs)


def update_workfile_template(*args):
    builder = AETemplateBuilder(registered_host())
    builder.rebuild_template()


def create_placeholder(*args):
    """Called when new workile placeholder should be created."""
    host = registered_host()
    builder = AETemplateBuilder(host)
    window = WorkfileBuildPlaceholderDialog(host, builder)
    window.exec_()


def update_placeholder(*args):
    """Called after placeholder item is selected to modify it."""
    host = registered_host()
    builder = AETemplateBuilder(host)

    stub = get_stub()
    selected_items = stub.get_selected_items(True, True, True)

    if len(selected_items) != 1:
        stub.print_msg("Please select just 1 placeholder")
        return

    selected_id = selected_items[0].id
    placeholder_item = None

    placeholder_items_by_id = {
        placeholder_item.scene_identifier: placeholder_item
        for placeholder_item in builder.get_placeholders()
    }
    for metadata_item in stub.get_metadata():
        if not metadata_item.get("is_placeholder"):
            continue
        if selected_id in metadata_item.get("members"):
            placeholder_item = placeholder_items_by_id.get(
                metadata_item["uuid"])
            break

    if not placeholder_item:
        stub.print_msg("Didn't find placeholder metadata. "
                       "Remove and re-create placeholder.")
        return

    window = WorkfileBuildPlaceholderDialog(host, builder)
    window.set_update_mode(placeholder_item)
    window.exec_()
