import inspect
import re

import ayon_maya.api.action
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    ValidateContentsOrder,
)
from ayon_maya.api.lib_rendersettings import RenderSettings
from ayon_maya.api import plugin
from maya import cmds


class ValidateRenderSingleCamera(plugin.MayaInstancePlugin,
                                 OptionalPyblishPluginMixin):
    """Validate renderable camera count for layer and <Camera> token.

    Pipeline is supporting multiple renderable cameras per layer, but image
    prefix must contain <Camera> token.
    """

    order = ValidateContentsOrder
    label = "Render Single Camera"
    families = ["renderlayer",
                "vrayscene"]
    actions = [ayon_maya.api.action.SelectInvalidAction]
    optional = False

    R_CAMERA_TOKEN = re.compile(r'%c|<camera>', re.IGNORECASE)

    def process(self, instance):
        """Process all the cameras in the instance"""
        if not self.is_active(instance.data):
            return
        invalid = self.get_invalid(instance)
        if invalid:
            raise PublishValidationError(
                "Invalid render cameras.",
                description=self.get_description()
            )

    @classmethod
    def get_invalid(cls, instance):

        cameras = instance.data.get("cameras", [])
        renderer = cmds.getAttr('defaultRenderGlobals.currentRenderer').lower()
        # handle various renderman names
        if renderer.startswith('renderman'):
            renderer = 'renderman'

        file_prefix = cmds.getAttr(
            RenderSettings.get_image_prefix_attr(renderer)
        )

        renderlayer = instance.data["renderlayer"]
        if len(cameras) > 1:
            if re.search(cls.R_CAMERA_TOKEN, file_prefix):
                # if there is <Camera> token in prefix and we have more then
                # 1 camera, all is ok.
                return
            cls.log.error(
                "Multiple renderable cameras found for %s: %s ",
                renderlayer, ", ".join(cameras))
            return [renderlayer] + cameras

        elif len(cameras) < 1:
            cls.log.error("No renderable cameras found for %s ", renderlayer)
            return [renderlayer]

    def get_description(self):
        return inspect.cleandoc(
            """### Render Cameras Invalid

            Your render cameras are misconfigured. You may have no render
            camera set or have multiple cameras with a render filename
            prefix that does not include the `<Camera>` token.

            See the logs for more details about the cameras.

            """
        )
