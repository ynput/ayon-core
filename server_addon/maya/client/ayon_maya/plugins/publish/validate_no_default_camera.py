import ayon_maya.api.action
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    ValidateContentsOrder,
)
from ayon_maya.api import plugin
from maya import cmds


def _as_report_list(values, prefix="- ", suffix="\n"):
    """Return list as bullet point list for a report"""
    if not values:
        return ""
    return prefix + (suffix + prefix).join(values)


class ValidateNoDefaultCameras(plugin.MayaInstancePlugin,
                               OptionalPyblishPluginMixin):
    """Ensure no default (startup) cameras are in the instance.

    This might be unnecessary. In the past there were some issues with
    referencing/importing files that contained the start up cameras overriding
    settings when being loaded and sometimes being skipped.
    """

    order = ValidateContentsOrder
    families = ['camera']
    label = "No Default Cameras"
    actions = [ayon_maya.api.action.SelectInvalidAction]
    optional = False

    @staticmethod
    def get_invalid(instance):
        cameras = cmds.ls(instance, type='camera', long=True)
        return [cam for cam in cameras if
                cmds.camera(cam, query=True, startupCamera=True)]

    def process(self, instance):
        """Process all the cameras in the instance"""
        if not self.is_active(instance.data):
            return
        invalid = self.get_invalid(instance)
        if invalid:
            raise PublishValidationError(
                "Default cameras found:\n\n{0}".format(
                    _as_report_list(sorted(invalid))
                ),
                title="Default cameras"
            )
