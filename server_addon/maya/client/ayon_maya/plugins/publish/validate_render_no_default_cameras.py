import ayon_maya.api.action
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    ValidateContentsOrder,
)
from ayon_maya.api import plugin
from maya import cmds


class ValidateRenderNoDefaultCameras(plugin.MayaInstancePlugin,
                                     OptionalPyblishPluginMixin):
    """Ensure no default (startup) cameras are to be rendered."""

    order = ValidateContentsOrder
    families = ['renderlayer']
    label = "No Default Cameras Renderable"
    actions = [ayon_maya.api.action.SelectInvalidAction]
    optional = False

    @staticmethod
    def get_invalid(instance):

        renderable = set(instance.data["cameras"])

        # Collect default cameras
        cameras = cmds.ls(type='camera', long=True)
        defaults = set(cam for cam in cameras if
                       cmds.camera(cam, query=True, startupCamera=True))

        return [cam for cam in renderable if cam in defaults]

    def process(self, instance):
        """Process all the cameras in the instance"""
        if not self.is_active(instance.data):
            return
        invalid = self.get_invalid(instance)
        if invalid:
            raise PublishValidationError(
                title="Rendering default cameras",
                message="Renderable default cameras "
                        "found: {0}".format(invalid))
