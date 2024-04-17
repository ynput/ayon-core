import inspect
import uuid
from collections import defaultdict
import pyblish.api

import ayon_core.hosts.maya.api.action
from ayon_core.hosts.maya.api import lib
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin, PublishValidationError, ValidatePipelineOrder)
from ayon_api import get_folders


def is_valid_uuid(value) -> bool:
    """Return whether value is a valid UUID"""
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


class ValidateNodeIDsRelated(pyblish.api.InstancePlugin,
                             OptionalPyblishPluginMixin):
    """Validate nodes have a related `cbId` to the instance.data[folderPath]"""

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

            invalid_list = "\n".join(f"- {node}" for node in sorted(invalid))

            raise PublishValidationError((
                "Nodes IDs found that are not related to folder '{}':\n{}"
                ).format(instance.data["folderPath"], invalid_list),
                description=self.get_description()
            )

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

            # Remove folder ids that are not valid UUID identifiers, these
            # may be legacy OpenPype ids
            other_folder_ids = {folder_id for folder_id in other_folder_ids
                                if is_valid_uuid(folder_id)}
            if not other_folder_ids:
                return invalid

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
                    "Found nodes related to other folders:\n{}".format(
                        "\n".join(f"- {path}" for path in sorted(folder_paths))
                    )
                )

        return invalid

    @staticmethod
    def get_description():
        return inspect.cleandoc("""### Node IDs must match folder id
        
        The node ids must match the folder entity id you are publishing to.
        
        Usually these mismatch occurs if you are re-using nodes from another 
        folder or project. 
        
        #### How to repair?
        
        The repair action will regenerate new ids for 
        the invalid nodes to match the instance's folder.
        """)
