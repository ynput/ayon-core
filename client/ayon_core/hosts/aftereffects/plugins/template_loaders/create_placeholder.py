from ayon_core.pipeline.workfile.workfile_template_builder import (
    CreatePlaceholderItem,
    PlaceholderCreateMixin
)
from ayon_core.hosts.aftereffects.api import get_stub
from ayon_core.hosts.aftereffects.api.lib import set_settings
import ayon_core.hosts.aftereffects.api.workfile_template_builder as wtb


class AEPlaceholderCreatePlugin(wtb.AEPlaceholderPlugin,
                                PlaceholderCreateMixin):
    """Adds Create placeholder.

    This adds composition and runs Create
    """
    identifier = "aftereffects.create"
    label = "AfterEffects create"

    item_type = CreatePlaceholderItem

    def create_placeholder(self, placeholder_data):
        stub = get_stub()
        name = "CREATEPLACEHOLDER"
        item_id = stub.add_item(name, "COMP")

        self._imprint_item(item_id, name, placeholder_data, stub)

    def populate_placeholder(self, placeholder):
        """Replace 'placeholder' with publishable instance.

        Renames prepared composition name, creates publishable instance, sets
        frame/duration settings according to DB.
        """
        pre_create_data = {"use_selection": True}
        item_id, item = self._get_item(placeholder)
        get_stub().select_items([item_id])
        self.populate_create_placeholder(placeholder, pre_create_data)

        # apply settings for populated composition
        item_id, metadata_item = self._get_item(placeholder)
        set_settings(True, True, [item_id])

    def get_placeholder_options(self, options=None):
        return self.get_create_plugin_options(options)
