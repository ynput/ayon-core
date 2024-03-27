from collections import defaultdict
from maya import cmds

import pyblish.api
import ayon_core.hosts.maya.api.action
from ayon_core.pipeline.publish import (
    RepairAction,
    ValidateContentsOrder,
    PublishValidationError
)


class ValidateLookIdReferenceEdits(pyblish.api.InstancePlugin):
    """Validate nodes in look have no reference edits to cbId.

    Note:
        This only validates the cbId edits on the referenced nodes that are
        used in the look. For example, a transform can have its cbId changed
        without being invalidated when it is not used in the look's assignment.

    """

    order = ValidateContentsOrder
    families = ['look']
    hosts = ['maya']
    label = 'Look Id Reference Edits'
    actions = [ayon_core.hosts.maya.api.action.SelectInvalidAction,
               RepairAction]

    @classmethod
    def apply_settings(cls, project_settings):
        # Disable plug-in if cbId workflow is disabled
        if not project_settings["maya"].get("use_cbid_workflow", True):
            cls.enabled = False
            return

    def process(self, instance):
        invalid = self.get_invalid(instance)

        if invalid:
            raise PublishValidationError("Invalid nodes %s" % (invalid,))

    @staticmethod
    def get_invalid(instance):

        # Collect all referenced members
        references = defaultdict(set)
        relationships = instance.data["lookData"]["relationships"]
        for relationship in relationships.values():
            for member in relationship['members']:
                node = member["name"]

                if cmds.referenceQuery(node, isNodeReferenced=True):
                    ref = cmds.referenceQuery(node, referenceNode=True)
                    references[ref].add(node)

        # Validate whether any has changes to 'cbId' attribute
        invalid = list()
        for ref, nodes in references.items():
            edits = cmds.referenceQuery(editAttrs=True,
                                        editNodes=True,
                                        showDagPath=True,
                                        showNamespace=True,
                                        onReferenceNode=ref)
            for edit in edits:

                # Ensure it is an attribute ending with .cbId
                # thus also ignore just node edits (like parenting)
                if not edit.endswith(".cbId"):
                    continue

                # Ensure the attribute is 'cbId' (and not a nested attribute)
                node, attr = edit.split(".", 1)
                if attr != "cbId":
                    continue

                if node in nodes:
                    invalid.append(node)

        return invalid

    @classmethod
    def repair(cls, instance):

        invalid = cls.get_invalid(instance)

        # Group invalid nodes by reference node
        references = defaultdict(set)
        for node in invalid:
            ref = cmds.referenceQuery(node, referenceNode=True)
            references[ref].add(node)

        # Remove the reference edits on the nodes per reference node
        for ref, nodes in references.items():
            for node in nodes:

                # Somehow this only works if you run the the removal
                # per edit command.
                for command in ["addAttr",
                                "connectAttr",
                                "deleteAttr",
                                "disconnectAttr",
                                "setAttr"]:
                    cmds.referenceEdit("{}.cbId".format(node),
                                       removeEdits=True,
                                       successfulEdits=True,
                                       failedEdits=True,
                                       editCommand=command,
                                       onReferenceNode=ref)
