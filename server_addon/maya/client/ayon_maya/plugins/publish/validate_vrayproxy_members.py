import ayon_maya.api.action
import pyblish.api
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
)
from ayon_maya.api import plugin
from maya import cmds


class ValidateVrayProxyMembers(plugin.MayaInstancePlugin,
                               OptionalPyblishPluginMixin):
    """Validate whether the V-Ray Proxy instance has shape members"""

    order = pyblish.api.ValidatorOrder
    label = 'VRay Proxy Members'
    families = ['vrayproxy']
    actions = [ayon_maya.api.action.SelectInvalidAction]
    optional = False

    def process(self, instance):
        if not self.is_active(instance.data):
            return
        invalid = self.get_invalid(instance)

        if invalid:
            raise PublishValidationError("'%s' is invalid VRay Proxy for "
                               "export!" % instance.name)

    @classmethod
    def get_invalid(cls, instance):

        shapes = cmds.ls(instance,
                         shapes=True,
                         noIntermediate=True,
                         long=True)

        if not shapes:
            cls.log.error("'%s' contains no shapes." % instance.name)

            # Return the instance itself
            return [instance.name]
