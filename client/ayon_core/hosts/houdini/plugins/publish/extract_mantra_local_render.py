import pyblish.api

from ayon_core.pipeline import publish
from ayon_core.hosts.houdini.api.lib import render_rop
import hou


class ExtractMantraLocalRender(publish.Extractor):

    order = pyblish.api.ExtractorOrder
    label = "Extract Mantra Local Render"
    hosts = ["houdini"]
    families = ["mantra_rop"]
    targets = ["local", "remote"]

    def process(self, instance):
        if instance.data.get("farm"):
            self.log.debug("Should be processed on farm, skipping.")
            return

        creator_attribute = instance.data["creator_attributes"]
        skip_render = creator_attribute["skip_render"]

        if skip_render:
            self.log.debug("Skip render is enabled, skipping rendering.")
            return

        ropnode = hou.node(instance.data.get("instance_node"))
        render_rop(ropnode)
