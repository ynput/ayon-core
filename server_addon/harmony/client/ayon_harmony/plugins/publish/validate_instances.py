import pyblish.api

import ayon_harmony.api as harmony
from ayon_core.pipeline import get_current_folder_path
from ayon_core.pipeline.publish import (
    ValidateContentsOrder,
    PublishXmlValidationError,
)


class ValidateInstanceRepair(pyblish.api.Action):
    """Repair the instance."""

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

        folder_path = get_current_folder_path()
        for instance in instances:
            data = harmony.read(instance.data["setMembers"][0])
            data["folderPath"] = folder_path
            harmony.imprint(instance.data["setMembers"][0], data)


class ValidateInstance(pyblish.api.InstancePlugin):
    """Validate the instance folder is the current folder."""

    label = "Validate Instance"
    hosts = ["harmony"]
    actions = [ValidateInstanceRepair]
    order = ValidateContentsOrder

    def process(self, instance):
        instance_folder_path = instance.data["folderPath"]
        current_colder_path = get_current_folder_path()
        msg = (
            "Instance folder is not the same as current folder:"
            f"\nInstance: {instance_folder_path}]"
            f"\nCurrent: {current_colder_path}"
        )

        formatting_data = {
            "found": instance_folder_path,
            "expected": current_colder_path
        }
        if instance_folder_path != current_colder_path:
            raise PublishXmlValidationError(self, msg,
                                            formatting_data=formatting_data)
