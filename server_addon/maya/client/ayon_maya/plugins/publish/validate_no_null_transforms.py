import ayon_maya.api.action
import maya.cmds as cmds
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    RepairAction,
    ValidateContentsOrder,
)
from ayon_maya.api import plugin


def _as_report_list(values, prefix="- ", suffix="\n"):
    """Return list as bullet point list for a report"""
    if not values:
        return ""
    return prefix + (suffix + prefix).join(values)


def has_shape_children(node):
    # Check if any descendants
    all_descendents = cmds.listRelatives(node,
                                         allDescendents=True,
                                         fullPath=True)
    if not all_descendents:
        return False

    # Check if there are any shapes at all
    shapes = cmds.ls(all_descendents, shapes=True, noIntermediate=True)
    if not shapes:
        return False

    return True


class ValidateNoNullTransforms(plugin.MayaInstancePlugin,
                               OptionalPyblishPluginMixin):
    """Ensure no null transforms are in the scene.

    Warning:
        Transforms with only intermediate shapes are also considered null
        transforms. These transform nodes could potentially be used in your
        construction history, so take care when automatically fixing this or
        when deleting the empty transforms manually.

    """

    order = ValidateContentsOrder
    families = ['model']
    label = 'No Empty/Null Transforms'
    actions = [RepairAction,
               ayon_maya.api.action.SelectInvalidAction]
    optional = False

    @staticmethod
    def get_invalid(instance):
        """Return invalid transforms in instance"""

        transforms = cmds.ls(instance, type='transform', long=True)

        invalid = []
        for transform in transforms:
            if not has_shape_children(transform):
                invalid.append(transform)

        return invalid

    def process(self, instance):
        """Process all the transform nodes in the instance """
        if not self.is_active(instance.data):
            return
        invalid = self.get_invalid(instance)
        if invalid:
            raise PublishValidationError(
                "Empty transforms found without shapes:\n\n{0}".format(
                    _as_report_list(sorted(invalid))
                ),
                title="Empty transforms"
            )

    @classmethod
    def repair(cls, instance):
        """Delete all null transforms.

        Note: If the node is used elsewhere (eg. connection to attributes or
        in history) deletion might mess up things.

        """
        invalid = cls.get_invalid(instance)
        if invalid:
            cmds.delete(invalid)
