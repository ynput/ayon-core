import pyblish.api

from ayon_core.pipeline import get_current_folder_path
from ayon_core.pipeline.publish import (
    ValidateContentsOrder,
    PublishXmlValidationError,
    OptionalPyblishPluginMixin
)
from ayon_photoshop import api as photoshop


class ValidateInstanceFolderRepair(pyblish.api.Action):
    """Repair the instance folder."""

    label = "Repair"
    icon = "wrench"
    on = "failed"

    def process(self, context, plugin):

        # Get the errored instances
        failed = []
        for result in context.data["results"]:
            if (
                result["error"] is not None
                and result["instance"] is not None
                and result["instance"] not in failed
            ):
                failed.append(result["instance"])

        # Apply pyblish.logic to get the instances for the plug-in
        instances = pyblish.api.instances_by_plugin(failed, plugin)
        stub = photoshop.stub()
        current_folder_path = get_current_folder_path()
        for instance in instances:
            data = stub.read(instance[0])
            data["folderPath"] = current_folder_path
            stub.imprint(instance[0], data)


class ValidateInstanceAsset(OptionalPyblishPluginMixin,
                            pyblish.api.InstancePlugin):
    """Validate the instance folder is the current selected context folder.

    As it might happen that multiple worfiles are opened, switching
    between them would mess with selected context.
    In that case outputs might be output under wrong folder!

    Repair action will use Context folder value (from Workfiles or Launcher)
    Closing and reopening with Workfiles will refresh  Context value.
    """

    label = "Validate Instance Folder"
    hosts = ["photoshop"]
    optional = True
    actions = [ValidateInstanceFolderRepair]
    order = ValidateContentsOrder

    def process(self, instance):
        instance_folder_path = instance.data["folderPath"]
        current_folder_path = get_current_folder_path()

        if instance_folder_path != current_folder_path:
            msg = (
                f"Instance folder {instance_folder_path} is not the same"
                f" as current context {current_folder_path}."

            )
            repair_msg = (
                "Repair with 'Repair' button"
                f" to use '{current_folder_path}'.\n"
            )
            formatting_data = {"msg": msg,
                               "repair_msg": repair_msg}
            raise PublishXmlValidationError(self, msg,
                                            formatting_data=formatting_data)
