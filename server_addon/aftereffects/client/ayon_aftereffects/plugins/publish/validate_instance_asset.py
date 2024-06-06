import pyblish.api

from ayon_core.pipeline import get_current_folder_path
from ayon_core.pipeline.publish import (
    ValidateContentsOrder,
    PublishXmlValidationError,
)
from ayon_aftereffects.api import get_stub


class ValidateInstanceFolderRepair(pyblish.api.Action):
    """Repair the instance folder with value from Context."""

    label = "Repair"
    icon = "wrench"
    on = "failed"

    def process(self, context, plugin):

        # Get the errored instances
        failed = []
        for result in context.data["results"]:
            if (result["error"] is not None and result["instance"] is not None
                    and result["instance"] not in failed):
                failed.append(result["instance"])

        # Apply pyblish.logic to get the instances for the plug-in
        instances = pyblish.api.instances_by_plugin(failed, plugin)
        stub = get_stub()
        for instance in instances:
            data = stub.read(instance[0])

            data["folderPath"] = get_current_folder_path()
            stub.imprint(instance[0].instance_id, data)


class ValidateInstanceFolder(pyblish.api.InstancePlugin):
    """Validate the instance folder is the current selected context folder.

        As it might happen that multiple worfiles are opened at same time,
        switching between them would mess with selected context. (From Launcher
        or Ftrack).

        In that case outputs might be output under wrong folder!

        Repair action will use Context folder value (from Workfiles or Launcher)
        Closing and reopening with Workfiles will refresh  Context value.
    """

    label = "Validate Instance Folder"
    hosts = ["aftereffects"]
    actions = [ValidateInstanceFolderRepair]
    order = ValidateContentsOrder

    def process(self, instance):
        instance_folder = instance.data["folderPath"]
        current_folder = get_current_folder_path()
        msg = (
            f"Instance folder {instance_folder} is not the same "
            f"as current context {current_folder}."
        )

        if instance_folder != current_folder:
            raise PublishXmlValidationError(self, msg)
