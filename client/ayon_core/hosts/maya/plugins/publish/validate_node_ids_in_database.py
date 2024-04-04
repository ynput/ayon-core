import pyblish.api
import ayon_api

import ayon_core.hosts.maya.api.action
from ayon_core.hosts.maya.api import lib
from ayon_core.pipeline.publish import (
    PublishValidationError, ValidatePipelineOrder)


class ValidateNodeIdsInDatabase(pyblish.api.InstancePlugin):
    """Validate if the CB Id is related to an folder in the database

    All nodes with the `cbId` attribute will be validated to ensure that
    the loaded asset in the scene is related to the current project.

    Tip: If there is an asset which is being reused from a different project
    please ensure the asset is republished in the new project

    """

    order = ValidatePipelineOrder
    label = 'Node Ids in Database'
    hosts = ['maya']
    families = ["*"]

    actions = [ayon_core.hosts.maya.api.action.SelectInvalidAction,
               ayon_core.hosts.maya.api.action.GenerateUUIDsOnInvalidAction]

    @classmethod
    def apply_settings(cls, project_settings):
        # Disable plug-in if cbId workflow is disabled
        if not project_settings["maya"].get("use_cbid_workflow", True):
            cls.enabled = False
            return

    def process(self, instance):
        invalid = self.get_invalid(instance)
        if invalid:
            raise PublishValidationError(
                ("Found folder ids which are not related to "
                 "current project in instance: `{}`").format(instance.name))

    @classmethod
    def get_invalid(cls, instance):

        invalid = []

        # Get all id required nodes
        id_required_nodes = lib.get_id_required_nodes(referenced_nodes=True,
                                                      nodes=instance[:])

        # check ids against database ids
        project_name = instance.context.data["projectName"]
        folder_entities = ayon_api.get_folders(project_name, fields={"id"})
        folder_ids = {
            folder_entity["id"]
            for folder_entity in folder_entities
        }

        # Get all asset IDs
        for node in id_required_nodes:
            cb_id = lib.get_id(node)

            # Ignore nodes without id, those are validated elsewhere
            if not cb_id:
                continue

            folder_id = cb_id.split(":", 1)[0]
            if folder_id not in folder_ids:
                cls.log.error("`%s` has unassociated folder id" % node)
                invalid.append(node)

        return invalid
