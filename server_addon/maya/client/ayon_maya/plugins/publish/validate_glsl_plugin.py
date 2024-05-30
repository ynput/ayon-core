from maya import cmds

from ayon_core.pipeline.publish import (
    RepairAction,
    ValidateContentsOrder,
    PublishValidationError,
    OptionalPyblishPluginMixin
)
from ayon_maya.api import plugin


class ValidateGLSLPlugin(plugin.MayaInstancePlugin,
                         OptionalPyblishPluginMixin):
    """
    Validate if the asset uses GLSL Shader
    """

    order = ValidateContentsOrder + 0.15
    families = ['gltf']
    label = 'maya2glTF plugin'
    actions = [RepairAction]
    optional = False

    def process(self, instance):
        if not self.is_active(instance.data):
            return
        if not cmds.pluginInfo("maya2glTF", query=True, loaded=True):
            raise PublishValidationError("maya2glTF is not loaded")

    @classmethod
    def repair(cls, instance):
        """
        Repair instance by enabling the plugin
        """
        return cmds.loadPlugin("maya2glTF", quiet=True)
