import pyblish.api
from ayon_core.pipeline import (
    PublishXmlValidationError,
    OptionalPyblishPluginMixin,
)
from ayon_core.hosts.tvpaint.api.pipeline import (
    list_instances,
    write_instances,
)


class FixAssetNames(pyblish.api.Action):
    """Repair the asset names.

    Change instanace metadata in the workfile.
    """

    label = "Repair"
    icon = "wrench"
    on = "failed"

    def process(self, context, plugin):
        context_asset_name = context.data["folderPath"]
        old_instance_items = list_instances()
        new_instance_items = []
        for instance_item in old_instance_items:
            instance_asset_name = instance_item.get("folderPath")
            if (
                instance_asset_name
                and instance_asset_name != context_asset_name
            ):
                instance_item["folderPath"] = context_asset_name
            new_instance_items.append(instance_item)
        write_instances(new_instance_items)


class ValidateAssetName(
    OptionalPyblishPluginMixin,
    pyblish.api.ContextPlugin
):
    """Validate asset name present on instance.

    Asset name on instance should be the same as context's.
    """

    label = "Validate Asset Names"
    order = pyblish.api.ValidatorOrder
    hosts = ["tvpaint"]
    actions = [FixAssetNames]

    def process(self, context):
        if not self.is_active(context.data):
            return
        context_asset_name = context.data["folderPath"]
        for instance in context:
            asset_name = instance.data.get("folderPath")
            if asset_name and asset_name == context_asset_name:
                continue

            instance_label = (
                instance.data.get("label") or instance.data["name"]
            )

            raise PublishXmlValidationError(
                self,
                (
                    "Different asset name on instance then context's."
                    " Instance \"{}\" has asset name: \"{}\""
                    " Context asset name is: \"{}\""
                ).format(
                    instance_label, asset_name, context_asset_name
                ),
                formatting_data={
                    "expected_asset": context_asset_name,
                    "found_asset": asset_name
                }
            )
