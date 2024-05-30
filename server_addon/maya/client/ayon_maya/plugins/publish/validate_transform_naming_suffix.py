# -*- coding: utf-8 -*-
"""Plugin for validating naming conventions."""
import json

import ayon_maya.api.action
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    ValidateContentsOrder,
)
from ayon_maya.api import plugin
from maya import cmds


class ValidateTransformNamingSuffix(plugin.MayaInstancePlugin,
                                    OptionalPyblishPluginMixin):
    """Validates transform suffix based on the type of its children shapes.

    Suffices must be:
        - mesh:
            _GEO (regular geometry)
            _GES (geometry to be smoothed at render)
            _GEP (proxy geometry; usually not to be rendered)
            _OSD (open subdiv smooth at rendertime)
        - nurbsCurve: _CRV
        - nurbsSurface: _NRB
        - locator: _LOC
        - null/group: _GRP
    Suffices can also be overridden by project settings.

    .. warning::
        This grabs the first child shape as a reference and doesn't use the
        others in the check.

    """

    order = ValidateContentsOrder
    families = ["model"]
    optional = True
    label = "Suffix Naming Conventions"
    actions = [ayon_maya.api.action.SelectInvalidAction]
    SUFFIX_NAMING_TABLE = json.dumps({
        "mesh": ["_GEO", "_GES", "_GEP", "_OSD"],
        "nurbsCurve": ["_CRV"],
        "nurbsSurface": ["_NRB"],
        "locator": ["_LOC"],
        "group": ["_GRP"]
    })

    ALLOW_IF_NOT_IN_SUFFIX_TABLE = True

    @classmethod
    def get_table_for_invalid(cls):
        suffix_naming_table = json.loads(cls.SUFFIX_NAMING_TABLE)
        ss = [
            " - <b>{}</b>: {}".format(k, ", ".join(v))
            for k, v in suffix_naming_table.items()
        ]
        return "<br>".join(ss)

    @staticmethod
    def is_valid_name(
        node_name,
        shape_type,
        suffix_naming_table,
        allow_if_not_in_suffix_table
    ):
        """Return whether node's name is correct.

        The correctness for a transform's suffix is dependent on what
        `shape_type` it holds. E.g. a transform with a mesh might need and
        `_GEO` suffix.

        When `shape_type` is None the transform doesn't have any direct
        children shapes.

        Args:
            node_name (str): Node name.
            shape_type (str): Type of node.
            suffix_naming_table (dict): Mapping dict for suffixes.
            allow_if_not_in_suffix_table (bool): Default output.

        """
        if shape_type not in suffix_naming_table:
            return allow_if_not_in_suffix_table

        suffices = suffix_naming_table[shape_type]
        for suffix in suffices:
            if node_name.endswith(suffix):
                return True
        return False

    @classmethod
    def get_invalid(cls, instance):
        """Get invalid nodes in instance.

        Args:
            instance (:class:`pyblish.api.Instance`): published instance.

        """
        transforms = cmds.ls(instance, type="transform", long=True)

        invalid = []
        suffix_naming_table = json.loads(cls.SUFFIX_NAMING_TABLE)
        for transform in transforms:
            shapes = cmds.listRelatives(transform,
                                        shapes=True,
                                        fullPath=True,
                                        noIntermediate=True)

            shape_type = cmds.nodeType(shapes[0]) if shapes else "group"
            if not cls.is_valid_name(
                transform,
                shape_type,
                suffix_naming_table,
                cls.ALLOW_IF_NOT_IN_SUFFIX_TABLE
            ):
                invalid.append(transform)

        return invalid

    def process(self, instance):
        """Process all the nodes in the instance.

        Args:
            instance (:class:`pyblish.api.Instance`): published instance.

        """
        if not self.is_active(instance.data):
            return

        invalid = self.get_invalid(instance)
        if invalid:
            valid = self.get_table_for_invalid()

            names = "<br>".join(
                " - {}".format(node) for node in invalid
            )
            valid = valid.replace("\n", "<br>")

            raise PublishValidationError(
                title="Invalid naming suffix",
                message="Valid suffixes are:<br>{0}<br><br>"
                        "Incorrectly named geometry transforms:<br>{1}"
                        "".format(valid, names))
