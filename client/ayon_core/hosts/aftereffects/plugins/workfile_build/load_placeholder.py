from ayon_core.pipeline.workfile.workfile_template_builder import (
    LoadPlaceholderItem,
    PlaceholderLoadMixin
)
from ayon_core.hosts.aftereffects.api import get_stub
import ayon_core.hosts.aftereffects.api.workfile_template_builder as wtb


class AEPlaceholderLoadPlugin(wtb.AEPlaceholderPlugin, PlaceholderLoadMixin):
    identifier = "aftereffects.load"
    label = "AfterEffects load"

    def _create_placeholder_item(self, item_data) -> LoadPlaceholderItem:
        return LoadPlaceholderItem(
            scene_identifier=item_data["uuid"],
            data=item_data["data"],
            plugin=self
        )

    def create_placeholder(self, placeholder_data):
        """Creates AE's Placeholder item in Project items list.

         Sets dummy resolution/duration/fps settings, will be replaced when
         populated.
         """
        stub = get_stub()
        name = "LOADERPLACEHOLDER"
        item_id = stub.add_placeholder(name, 1920, 1060, 25, 10)

        self._imprint_item(item_id, name, placeholder_data, stub)

    def populate_placeholder(self, placeholder):
        """Use Openpype Loader from `placeholder` to create new FootageItems

        New FootageItems are created, files are imported.
        """
        self.populate_load_placeholder(placeholder)
        errors = placeholder.get_errors()
        stub = get_stub()
        if errors:
            stub.print_msg("\n".join(errors))
        else:
            if not placeholder.data["keep_placeholder"]:
                metadata = stub.get_metadata()
                for item in metadata:
                    if not item.get("is_placeholder"):
                        continue
                    scene_identifier = item.get("uuid")
                    if (scene_identifier and
                            scene_identifier == placeholder.scene_identifier):
                        stub.delete_item(item["members"][0])
                stub.remove_instance(placeholder.scene_identifier, metadata)

    def get_placeholder_options(self, options=None):
        return self.get_load_plugin_options(options)

    def load_succeed(self, placeholder, container):
        placeholder_item_id, _ = self._get_item(placeholder)
        item_id = container.id
        get_stub().add_item_instead_placeholder(placeholder_item_id, item_id)
