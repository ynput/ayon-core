import inspect

import pyblish.api
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    context_plugin_should_run,
)
from ayon_maya.api import plugin
from maya import cmds


class ValidateCurrentRenderLayerIsRenderable(plugin.MayaContextPlugin,
                                             OptionalPyblishPluginMixin):
    """Validate if current render layer has a renderable camera.

    There is a bug in Redshift which occurs when the current render layer
    at file open has no renderable camera. The error raised is as follows:

    "No renderable cameras found. Aborting render"

    This error is raised even if that render layer will not be rendered.

    """

    label = "Current Render Layer Has Renderable Camera"
    order = pyblish.api.ValidatorOrder
    families = ["renderlayer"]
    optional = False

    def process(self, context):
        if not self.is_active(context.data):
            return
        # Workaround bug pyblish-base#250
        if not context_plugin_should_run(self, context):
            return

        # This validator only makes sense when publishing renderlayer instances
        # with Redshift. We skip validation if there isn't any.
        if not any(self.is_active_redshift_render_instance(instance)
                   for instance in context):
            return

        cameras = cmds.ls(type="camera", long=True)
        renderable = any(c for c in cameras if cmds.getAttr(c + ".renderable"))
        if not renderable:
            layer = cmds.editRenderLayerGlobals(query=True,
                                                currentRenderLayer=True)
            raise PublishValidationError(
                "Current render layer '{}' has no renderable camera".format(
                    layer
                ),
                description=inspect.getdoc(self)
            )

    @staticmethod
    def is_active_redshift_render_instance(instance) -> bool:
        """Return whether instance is an active renderlayer instance set to
        render with Redshift renderer."""
        if not instance.data.get("active", True):
            return False

        # Check this before families just because it's a faster check
        if not instance.data.get("renderer") == "redshift":
            return False

        families = set()
        families.add(instance.data.get("family"))
        families.update(instance.data.get("families", []))
        if "renderlayer" not in families:
            return False

        return True
