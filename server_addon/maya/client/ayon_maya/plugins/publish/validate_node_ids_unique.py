from collections import defaultdict

import ayon_maya.api.action
from ayon_core.pipeline.publish import (
    PublishValidationError,
    ValidatePipelineOrder,
)
from ayon_maya.api import lib
from ayon_maya.api import plugin
from maya import cmds


class ValidateNodeIdsUnique(plugin.MayaInstancePlugin):
    """Validate the nodes in the instance have a unique Colorbleed Id

    Here we ensure that what has been added to the instance is unique
    """

    order = ValidatePipelineOrder
    label = 'Non Duplicate Instance Members (ID)'
    families = ["model",
                "look",
                "rig",
                "yetiRig"]

    actions = [ayon_maya.api.action.SelectInvalidAction,
               ayon_maya.api.action.GenerateUUIDsOnInvalidAction]

    @classmethod
    def apply_settings(cls, project_settings):
        # Disable plug-in if cbId workflow is disabled
        if not project_settings["maya"].get("use_cbid_workflow", True):
            cls.enabled = False
            return

    def process(self, instance):
        """Process all meshes"""

        # Ensure all nodes have a cbId
        invalid = self.get_invalid(instance)
        if invalid:
            label = "Nodes found with non-unique folder ids"
            raise PublishValidationError(
                message="{}, see log".format(label),
                title="Non-unique folder ids on nodes",
                description="{}\n- {}".format(label,
                                              "\n- ".join(sorted(invalid)))
            )

    @classmethod
    def get_invalid(cls, instance):
        """Return the member nodes that are invalid"""

        # Check only non intermediate shapes
        # todo: must the instance itself ensure to have no intermediates?
        # todo: how come there are intermediates?
        instance_members = cmds.ls(instance, noIntermediate=True, long=True)

        # Collect each id with their members
        ids = defaultdict(list)
        for member in instance_members:
            object_id = lib.get_id(member)
            if not object_id:
                continue
            ids[object_id].append(member)

        # Take only the ids with more than one member
        invalid = list()
        for members in ids.values():
            if len(members) > 1:
                members_text = "\n".join(
                    "- {}".format(member) for member in sorted(members)
                )
                cls.log.error(
                    "ID found on multiple nodes:\n{}".format(members_text)
                )
                invalid.extend(members)

        return invalid
