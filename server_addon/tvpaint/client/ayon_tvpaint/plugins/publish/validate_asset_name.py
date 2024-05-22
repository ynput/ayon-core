import pyblish.api
from ayon_core.pipeline import (
    PublishXmlValidationError,
    OptionalPyblishPluginMixin,
)
from ayon_tvpaint.api.pipeline import (
    list_instances,
    write_instances,
)


class FixFolderPaths(pyblish.api.Action):
    """Repair the folder paths.

    Change instanace metadata in the workfile.
    """

    label = "Repair"
    icon = "wrench"
    on = "failed"

    def process(self, context, plugin):
        context_folder_path = context.data["folderPath"]
        old_instance_items = list_instances()
        new_instance_items = []
        for instance_item in old_instance_items:
            instance_folder_path = instance_item.get("folderPath")
            if (
                instance_folder_path
                and instance_folder_path != context_folder_path
            ):
                instance_item["folderPath"] = context_folder_path
            new_instance_items.append(instance_item)
        write_instances(new_instance_items)


class ValidateAssetName(
    OptionalPyblishPluginMixin,
    pyblish.api.ContextPlugin
):
    """Validate folder path present on instance.

    Folder path on instance should be the same as context's.
    """

    label = "Validate Folder Paths"
    order = pyblish.api.ValidatorOrder
    hosts = ["tvpaint"]
    actions = [FixFolderPaths]

    settings_category = "tvpaint"

    def process(self, context):
        if not self.is_active(context.data):
            return
        context_folder_path = context.data["folderPath"]
        for instance in context:
            folder_path = instance.data.get("folderPath")
            if folder_path and folder_path == context_folder_path:
                continue

            instance_label = (
                instance.data.get("label") or instance.data["name"]
            )

            raise PublishXmlValidationError(
                self,
                (
                    "Different folder path on instance then context's."
                    " Instance \"{}\" has folder path: \"{}\""
                    " Context folder path is: \"{}\""
                ).format(
                    instance_label, folder_path, context_folder_path
                ),
                formatting_data={
                    "expected_folder": context_folder_path,
                    "found_folder": folder_path
                }
            )
