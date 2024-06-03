import os
import pyblish.api
import maya.cmds as cmds

from ayon_core.pipeline.publish import (
    RepairContextAction,
    PublishValidationError,
    OptionalPyblishPluginMixin
)
from ayon_maya.api import plugin


class ValidateLoadedPlugin(plugin.MayaInstancePlugin,
                           OptionalPyblishPluginMixin):
    """Ensure there are no unauthorized loaded plugins"""

    label = "Loaded Plugin"
    order = pyblish.api.ValidatorOrder
    actions = [RepairContextAction]
    optional = True

    @classmethod
    def get_invalid(cls, context):

        invalid = []
        loaded_plugins = cmds.pluginInfo(query=True, listPlugins=True)
        # get variable from AYON settings
        whitelist_native_plugins = cls.whitelist_native_plugins
        authorized_plugins = cls.authorized_plugins or []

        for maya_plugin in loaded_plugins:
            if not whitelist_native_plugins and os.getenv('MAYA_LOCATION') \
                    in cmds.pluginInfo(maya_plugin, query=True, path=True):
                continue
            if maya_plugin not in authorized_plugins:
                invalid.append(maya_plugin)

        return invalid

    def process(self, context):
        if not self.is_active(context.data):
            return
        invalid = self.get_invalid(context)
        if invalid:
            raise PublishValidationError(
                "Found forbidden plugin name: {}".format(", ".join(invalid))
            )

    @classmethod
    def repair(cls, context):
        """Unload forbidden plugins"""

        for maya_plugin in cls.get_invalid(context):
            cmds.pluginInfo(maya_plugin, edit=True, autoload=False)
            cmds.unloadPlugin(maya_plugin, force=True)
