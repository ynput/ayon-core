import ayon_maya.api.action
import pyblish.api
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
)
from ayon_maya.api import plugin


class ValidateAssemblyNamespaces(plugin.MayaInstancePlugin,
                                 OptionalPyblishPluginMixin):
    """Ensure namespaces are not nested.

    In the outliner an item in a normal namespace looks as following:
        props_desk_01_:modelDefault

    Any namespace which diverts from that is illegal, example of an illegal
    namespace:
        room_study_01_:props_desk_01_:modelDefault

    """

    label = "Validate Assembly Namespaces"
    order = pyblish.api.ValidatorOrder
    families = ["assembly"]
    actions = [ayon_maya.api.action.SelectInvalidAction]
    optional = False

    def process(self, instance):
        if not self.is_active(instance.data):
            return
        self.log.debug("Checking namespace for %s" % instance.name)
        if self.get_invalid(instance):
            raise PublishValidationError("Nested namespaces found")

    @classmethod
    def get_invalid(cls, instance):

        from maya import cmds

        invalid = []
        for item in cmds.ls(instance):
            item_parts = item.split("|", 1)[0].rsplit(":")
            if len(item_parts[:-1]) > 1:
                invalid.append(item)

        return invalid
