import ayon_maya.api.action
from ayon_core.pipeline.publish import (
    PublishValidationError,
    ValidateContentsOrder,
)
from ayon_maya.api import plugin


class ValidateInstanceHasMembers(plugin.MayaInstancePlugin):
    """Validates instance objectSet has *any* members."""

    order = ValidateContentsOrder
    label = 'Instance has members'
    actions = [ayon_maya.api.action.SelectInvalidAction]

    @classmethod
    def get_invalid(cls, instance):
        invalid = list()
        if not instance.data.get("setMembers"):
            objectset_name = instance.data['name']
            invalid.append(objectset_name)

        return invalid

    def process(self, instance):
        # Allow renderlayer, rendersetup and workfile to be empty
        skip_families = {"workfile", "renderlayer", "rendersetup"}
        if instance.data.get("productType") in skip_families:
            return

        invalid = self.get_invalid(instance)
        if invalid:
            # Invalid will always be a single entry, we log the single name
            name = invalid[0]
            raise PublishValidationError(
                title="Empty instance",
                message="Instance '{0}' is empty".format(name)
            )
