import pyblish.api
from ayon_core.pipeline import publish
from ayon_core.hosts.houdini.api import lib

import hou


class ExtractROP(publish.Extractor):
    """Render a ROP node and add representation to the instance"""

    label = "Extract ROP"
    families = ["rop"]
    hosts = ["houdini"]

    order = pyblish.api.ExtractorOrder + 0.1

    def process(self, instance):

        if instance.data.get('farm'):
            # Will be submitted to farm instead - not rendered locally
            return

        files = instance.data["frames"]
        first_file = files[0] if isinstance(files, (list, tuple)) else files
        _, ext = lib.splitext(
            first_file, allowed_multidot_extensions=[
                ".ass.gz", ".bgeo.sc", ".bgeo.gz",
                ".bgeo.lzma", ".bgeo.bz2"])
        ext = ext.lstrip(".")  # strip starting dot

        # prepare representation
        representation = {
            "name": ext,
            "ext": ext,
            "files": files,
            "stagingDir": instance.data["stagingDir"]
        }

        # render rop
        creator_attribute = instance.data["creator_attributes"]
        if creator_attribute.get("render_target") == "local":
            ropnode = hou.node(instance.data.get("instance_node"))
            lib.render_rop(ropnode)

        # add representation
        instance.data.setdefault("representations", []).append(representation)
