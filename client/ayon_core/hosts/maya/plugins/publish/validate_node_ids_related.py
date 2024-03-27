from collections import defaultdict
import pyblish.api

import ayon_core.hosts.maya.api.action
from ayon_core.hosts.maya.api import lib
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin, PublishValidationError, ValidatePipelineOrder)
from ayon_api import get_folders


class ValidateNodeIDsRelated(pyblish.api.InstancePlugin,
                             OptionalPyblishPluginMixin):
    """Validate nodes have a related Colorbleed Id to the
    instance.data[folderPath]

    """

    order = ValidatePipelineOrder
    label = 'Node Ids Related (ID)'
    hosts = ['maya']
    families = ["model",
                "look",
                "rig"]
    optional = True

    actions = [ayon_core.hosts.maya.api.action.SelectInvalidAction,
               ayon_core.hosts.maya.api.action.GenerateUUIDsOnInvalidAction]

    @classmethod
    def apply_settings(cls, project_settings):
        # Disable plug-in if cbId workflow is disabled
        if not project_settings["maya"].get("use_cbid_workflow", True):
            cls.enabled = False
            return

    def process(self, instance):
        """Process all nodes in instance (including hierarchy)"""
        if not self.is_active(instance.data):
            return

        # Ensure all nodes have a cbId
        invalid = self.get_invalid(instance)
        if invalid:
            raise PublishValidationError((
                "Nodes IDs found that are not related to folder '{}' : {}"
            ).format(
                instance.data["folderPath"], invalid
            ))

    @classmethod
    def get_invalid(cls, instance):
        """Return the member nodes that are invalid"""
        folder_id = instance.data["folderEntity"]["id"]

        # We do want to check the referenced nodes as it might be
        # part of the end product
        invalid = list()
        nodes_by_other_folder_ids = defaultdict(set)
        for node in instance:
            _id = lib.get_id(node)
            if not _id:
                continue

            node_folder_id = _id.split(":", 1)[0]
            if node_folder_id != folder_id:
                invalid.append(node)
                nodes_by_other_folder_ids[node_folder_id].add(node)

        # Log what other assets were found.
        if nodes_by_other_folder_ids:
            project_name = instance.context.data["projectName"]
            other_folder_ids = set(nodes_by_other_folder_ids.keys())
            folder_entities = get_folders(project_name=project_name,
                                          folder_ids=other_folder_ids,
                                          fields=["path"])
            if folder_entities:
                # Log names of other assets detected
                # We disregard logging nodes/ids for asset ids where no asset
                # was found in the database because ValidateNodeIdsInDatabase
                # takes care of that.
                folder_paths = {entity["path"] for entity in folder_entities}
                cls.log.error(
                    "Found nodes related to other assets: {}"
                    .format(", ".join(sorted(folder_paths)))
                )

        return invalid
