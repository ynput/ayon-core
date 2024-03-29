# -*- coding: utf-8 -*-
import pyblish.api
import hou
from ayon_core.pipeline import PublishValidationError
from ayon_core.pipeline.publish import RepairAction


class DisableSplitExportAction(RepairAction):
    label = "Disable Split Export"


class ValidateSplitExportIsDisabled(pyblish.api.InstancePlugin):
    """Validate the Instance has no current cooking errors."""

    order = pyblish.api.ValidatorOrder
    hosts = ["houdini"]
    families = ["mantra_rop",
                "redshift_rop"]
    label = "Validate Split Export Is Disabled"
    actions = [DisableSplitExportAction]

    def process(self, instance):

        invalid = self.get_invalid(instance)
        if invalid:
            nodes = [n.path() for n in invalid]
            raise PublishValidationError(
                "See log for details. "
                "Invalid nodes: {0}".format(nodes)
            )


    @classmethod
    def get_invalid(cls, instance):

        invalid = []
        rop_node = hou.node(instance.data["instance_node"])

        creator_attribute = instance.data["creator_attributes"]
        farm_enabled = creator_attribute["farm"]
        if farm_enabled:
            cls.log.debug(
                "Farm is enabled, skipping validation."
            )
            return


        split_enabled = creator_attribute["split_render"]
        if split_enabled:
            invalid.append(rop_node)
            cls.log.error(
                "Split Export must be disabled in local render instances."
            )

        return invalid

    @classmethod
    def repair(cls, instance):

        create_context = instance.context.data["create_context"]
        created_instance = create_context.get_instance_by_id(
            instance.data["instance_id"])
        creator_attributes = created_instance["creator_attributes"]
        # Disable export_job
        creator_attributes["split_render"] = False
        create_context.save_changes()
