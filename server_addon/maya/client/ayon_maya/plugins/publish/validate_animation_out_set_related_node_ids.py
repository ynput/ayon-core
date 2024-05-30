import ayon_maya.api.action
import maya.cmds as cmds
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishXmlValidationError,
    RepairAction,
    ValidateContentsOrder,
    apply_plugin_settings_automatically,
    get_plugin_settings,
)
from ayon_maya.api import lib
from ayon_maya.api import plugin


class ValidateOutRelatedNodeIds(plugin.MayaInstancePlugin,
                                OptionalPyblishPluginMixin):
    """Validate if deformed shapes have related IDs to the original shapes

    When a deformer is applied in the scene on a referenced mesh that already
    had deformers then Maya will create a new shape node for the mesh that
    does not have the original id. This validator checks whether the ids are
    valid on all the shape nodes in the instance.

    """

    order = ValidateContentsOrder
    families = ['animation', "pointcache", "proxyAbc"]
    hosts = ['maya']
    label = 'Animation Out Set Related Node Ids'
    actions = [
        ayon_maya.api.action.SelectInvalidAction,
        RepairAction
    ]
    optional = False

    @classmethod
    def apply_settings(cls, project_settings):
        # Preserve automatic settings applying logic
        settings = get_plugin_settings(plugin=cls,
                                       project_settings=project_settings,
                                       log=cls.log,
                                       category="maya")
        apply_plugin_settings_automatically(cls, settings, logger=cls.log)

        # Disable plug-in if cbId workflow is disabled
        if not project_settings["maya"].get("use_cbid_workflow", True):
            cls.enabled = False
            return

    def process(self, instance):
        """Process all meshes"""
        if not self.is_active(instance.data):
            return
        # Ensure all nodes have a cbId and a related ID to the original shapes
        # if a deformer has been created on the shape
        invalid = self.get_invalid(instance)
        if invalid:

            # Use the short names
            invalid = cmds.ls(invalid)
            invalid.sort()

            # Construct a human-readable list
            invalid = "\n".join("- {}".format(node) for node in invalid)

            raise PublishXmlValidationError(
                plugin=self,
                message=(
                    "Nodes have different IDs than their input "
                    "history: \n{0}".format(invalid)
                )
            )

    @classmethod
    def get_invalid(cls, instance):
        """Get all nodes which do not match the criteria"""

        invalid = []
        types = ["mesh", "nurbsCurve", "nurbsSurface"]

        # get asset id
        nodes = instance.data.get("out_hierarchy", instance[:])
        for node in cmds.ls(nodes, type=types, long=True):

            # We only check when the node is *not* referenced
            if cmds.referenceQuery(node, isNodeReferenced=True):
                continue

            # Get the current id of the node
            node_id = lib.get_id(node)

            history_id = lib.get_id_from_sibling(node)
            if history_id is not None and node_id != history_id:
                invalid.append(node)

        return invalid

    @classmethod
    def repair(cls, instance):

        for node in cls.get_invalid(instance):
            # Get the original id from history
            history_id = lib.get_id_from_sibling(node)
            if not history_id:
                cls.log.error("Could not find ID in history for '%s'", node)
                continue

            lib.set_id(node, history_id, overwrite=True)
