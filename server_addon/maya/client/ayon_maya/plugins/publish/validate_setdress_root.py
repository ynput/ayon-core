from ayon_core.pipeline.publish import (
    PublishValidationError,
    ValidateContentsOrder,
)
from ayon_maya.api import plugin


class ValidateSetdressRoot(plugin.MayaInstancePlugin):
    """Validate if set dress top root node is published."""

    order = ValidateContentsOrder
    label = "SetDress Root"
    families = ["setdress"]

    def process(self, instance):
        from maya import cmds

        if instance.data.get("exactSetMembersOnly"):
            return

        set_member = instance.data["setMembers"]
        root = cmds.ls(set_member, assemblies=True, long=True)

        if not root or root[0] not in set_member:
            raise PublishValidationError(
                "Setdress top root node is not being published."
            )
