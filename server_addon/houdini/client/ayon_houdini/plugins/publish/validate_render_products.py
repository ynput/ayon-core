# -*- coding: utf-8 -*-
import inspect

import pyblish.api
from ayon_core.pipeline import PublishValidationError
from ayon_core.hosts.houdini.api.action import SelectROPAction

import hou


class ValidateUsdRenderProducts(pyblish.api.InstancePlugin):
    """Validate at least one render product is present"""

    order = pyblish.api.ValidatorOrder
    families = ["usdrender"]
    hosts = ["houdini"]
    label = "Validate Render Products"
    actions = [SelectROPAction]

    def get_description(self):
        return inspect.cleandoc(
            """### No Render Products

            The render submission specified no Render Product outputs and
            as such would not generate any rendered files.

            This is usually the case if no Render Settings or Render
            Products were created.

            Make sure to create the Render Settings
            relevant to the renderer you want to use.

            """
        )

    def process(self, instance):

        if not instance.data.get("output_node"):
            self.log.warning("No valid LOP node to render found.")
            return

        if not instance.data.get("files", []):
            node_path = instance.data["instance_node"]
            node = hou.node(node_path)
            rendersettings_path = (
                node.evalParm("rendersettings") or "/Render/rendersettings"
            )
            raise PublishValidationError(
                message=(
                    "No Render Products found in Render Settings "
                    "for '{}' at '{}'".format(node_path, rendersettings_path)
                ),
                description=self.get_description(),
                title=self.label
            )
