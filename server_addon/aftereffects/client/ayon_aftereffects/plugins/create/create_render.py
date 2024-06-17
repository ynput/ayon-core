import re

from ayon_core import resources
from ayon_core.lib import BoolDef, UISeparatorDef
from ayon_core.pipeline import (
    Creator,
    CreatedInstance,
    CreatorError
)
from ayon_core.lib import prepare_template_data
from ayon_core.pipeline.create import PRODUCT_NAME_ALLOWED_SYMBOLS
from ayon_aftereffects import api
from ayon_aftereffects.api.pipeline import cache_and_get_instances
from ayon_aftereffects.api.lib import set_settings


class RenderCreator(Creator):
    """Creates 'render' instance for publishing.

    Result of 'render' instance is video or sequence of images for particular
    composition based of configuration in its RenderQueue.
    """
    identifier = "render"
    label = "Render"
    product_type = "render"
    description = "Render creator"

    create_allow_context_change = True

    # Settings
    mark_for_review = True
    force_setting_values = True

    def create(self, product_name, data, pre_create_data):
        stub = api.get_stub()  # only after After Effects is up

        try:
            _ = stub.get_active_document_full_name()
        except ValueError:
            raise CreatorError(
                "Please save workfile via Workfile app first!"
            )

        if pre_create_data.get("use_selection"):
            comps = stub.get_selected_items(
                comps=True, folders=False, footages=False
            )
        else:
            comps = stub.get_items(comps=True, folders=False, footages=False)

        if not comps:
            raise CreatorError(
                "Nothing to create. Select composition in Project Bin if "
                "'Use selection' is toggled or create at least "
                "one composition."
            )
        use_composition_name = (pre_create_data.get("use_composition_name") or
                                len(comps) > 1)
        for comp in comps:
            composition_name = re.sub(
                "[^{}]+".format(PRODUCT_NAME_ALLOWED_SYMBOLS),
                "",
                comp.name
            )
            if use_composition_name:
                if "{composition}" not in product_name.lower():
                    product_name += "{Composition}"

                dynamic_fill = prepare_template_data({"composition":
                                                      composition_name})
                comp_product_name = product_name.format(**dynamic_fill)
                data["composition_name"] = composition_name
            else:
                comp_product_name = re.sub(
                    r"\{composition\}",
                    "",
                    product_name,
                    flags=re.IGNORECASE
                )

            for inst in self.create_context.instances:
                if comp_product_name == inst.product_name:
                    raise CreatorError("{} already exists".format(
                        inst.product_name))

            data["members"] = [comp.id]
            data["orig_comp_name"] = composition_name

            new_instance = CreatedInstance(
                self.product_type, comp_product_name, data, self
            )
            if "farm" in pre_create_data:
                use_farm = pre_create_data["farm"]
                new_instance.creator_attributes["farm"] = use_farm

            review = pre_create_data["mark_for_review"]
            new_instance.creator_attributes["mark_for_review"] = review

            api.get_stub().imprint(new_instance.id,
                                   new_instance.data_to_store())
            self._add_instance_to_context(new_instance)

            stub.rename_item(comp.id, comp_product_name)
            if self.force_setting_values:
                set_settings(True, True, [comp.id], print_msg=False)

    def get_pre_create_attr_defs(self):
        output = [
            BoolDef("use_selection",
                    tooltip="Composition for publishable instance should be "
                            "selected by default.",
                    default=True, label="Use selection"),
            BoolDef("use_composition_name",
                    label="Use composition name in product"),
            UISeparatorDef(),
            BoolDef("farm", label="Render on farm"),
            BoolDef(
                "mark_for_review",
                label="Review",
                default=self.mark_for_review
            )
        ]
        return output

    def get_instance_attr_defs(self):
        return [
            BoolDef("farm", label="Render on farm"),
            BoolDef(
                "mark_for_review",
                label="Review",
                default=False
            )
        ]

    def get_icon(self):
        return resources.get_openpype_splash_filepath()

    def collect_instances(self):
        for instance_data in cache_and_get_instances(self):
            # legacy instances have product_type=='render' or 'renderLocal', use them
            creator_id = instance_data.get("creator_identifier")
            if not creator_id:
                # NOTE this is for backwards compatibility but probably can be
                #   removed
                creator_id = instance_data.get("family", "")
                creator_id = creator_id.replace("Local", "")

            if creator_id == self.identifier:
                instance_data = self._handle_legacy(instance_data)
                instance = CreatedInstance.from_existing(
                    instance_data, self
                )
                self._add_instance_to_context(instance)

    def update_instances(self, update_list):
        for created_inst, _changes in update_list:
            api.get_stub().imprint(created_inst.get("instance_id"),
                                   created_inst.data_to_store())
            name_change = _changes.get("productName")
            if name_change:
                api.get_stub().rename_item(created_inst.data["members"][0],
                                           name_change.new_value)

    def remove_instances(self, instances):
        """Removes metadata and renames to original comp name if available."""
        for instance in instances:
            self._remove_instance_from_context(instance)
            self.host.remove_instance(instance)

            comp_id = instance.data["members"][0]
            comp = api.get_stub().get_item(comp_id)
            orig_comp_name = instance.data.get("orig_comp_name")
            if comp:
                if orig_comp_name:
                    new_comp_name = orig_comp_name
                else:
                    new_comp_name = "dummyCompName"
                api.get_stub().rename_item(comp_id,
                                           new_comp_name)

    def apply_settings(self, project_settings):
        plugin_settings = (
            project_settings["aftereffects"]["create"]["RenderCreator"]
        )

        self.mark_for_review = plugin_settings["mark_for_review"]
        self.default_variants = plugin_settings.get(
            "default_variants",
            plugin_settings.get("defaults") or []
        )

    def get_detail_description(self):
        return """Creator for Render instances

        Main publishable item in AfterEffects will be of `render` product type.
        Result of this item (instance) is picture sequence or video that could
        be a final delivery product or loaded and used in another DCCs.

        Select single composition and create instance of 'render' product type
        or turn off 'Use selection' to create instance for all compositions.

        'Use composition name in product' allows to explicitly add composition
        name into created product name.

        Position of composition name could be set in
        `project_settings/global/tools/creator/product_name_profiles` with
        some form of '{composition}' placeholder.

        Composition name will be used implicitly if multiple composition should
        be handled at same time.

        If {composition} placeholder is not us 'product_name_profiles'
        composition name will be capitalized and set at the end of
        product name if necessary.

        If composition name should be used, it will be cleaned up of characters
        that would cause an issue in published file names.
        """

    def get_dynamic_data(
        self,
        project_name,
        folder_entity,
        task_entity,
        variant,
        host_name,
        instance
    ):
        dynamic_data = {}
        if instance is not None:
            composition_name = instance.get("composition_name")
            if composition_name:
                dynamic_data["composition"] = composition_name
        else:
            dynamic_data["composition"] = "{composition}"

        return dynamic_data

    def _handle_legacy(self, instance_data):
        """Converts old instances to new format."""
        if not instance_data.get("members"):
            instance_data["members"] = [instance_data.get("uuid")]

        if instance_data.get("uuid"):
            # uuid not needed, replaced with unique instance_id
            api.get_stub().remove_instance(instance_data.get("uuid"))
            instance_data.pop("uuid")

        if not instance_data.get("task"):
            instance_data["task"] = self.create_context.get_current_task_name()

        if not instance_data.get("creator_attributes"):
            is_old_farm = instance_data.get("family") != "renderLocal"
            instance_data["creator_attributes"] = {"farm": is_old_farm}
            instance_data["productType"] = self.product_type

        if instance_data["creator_attributes"].get("mark_for_review") is None:
            instance_data["creator_attributes"]["mark_for_review"] = True

        return instance_data
