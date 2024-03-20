from maya import cmds

import pyblish.api
import ayon_core.hosts.maya.api.action
from ayon_core.pipeline.publish import (
    ValidateContentsOrder,
    OptionalPyblishPluginMixin
)

class ValidateUniqueNames(pyblish.api.Validator,
                          OptionalPyblishPluginMixin):
    """transform names should be unique

    ie: using cmds.ls(someNodeName) should always return shortname

    """

    order = ValidateContentsOrder
    hosts = ["maya"]
    families = ["model"]
    label = "Unique transform name"
    actions = [ayon_core.hosts.maya.api.action.SelectInvalidAction]
    optional = True

    @staticmethod
    def get_invalid(instance):
        """Returns the invalid transforms in the instance.

        Returns:
            list: Non-unique name transforms.

        """

        return [tr for tr in cmds.ls(instance, type="transform")
                if '|' in tr]

    def process(self, instance):
        """Process all the nodes in the instance "objectSet"""
        if not self.is_active(instance.data):
            return
        invalid = self.get_invalid(instance)
        if invalid:
            raise ValueError("Nodes found with none unique names. "
                             "values: {0}".format(invalid))
