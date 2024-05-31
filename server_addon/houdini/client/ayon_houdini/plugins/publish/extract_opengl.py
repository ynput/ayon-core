import os
import hou

import pyblish.api

from ayon_core.pipeline import publish
from ayon_houdini.api import plugin
from ayon_houdini.api.lib import render_rop


class ExtractOpenGL(plugin.HoudiniExtractorPlugin,
                    publish.ColormanagedPyblishPluginMixin):

    order = pyblish.api.ExtractorOrder - 0.01
    label = "Extract OpenGL"
    families = ["review"]

    def process(self, instance):
        ropnode = hou.node(instance.data.get("instance_node"))

        # This plugin is triggered when marking render as reviewable.
        # Therefore, this plugin will run on over wrong instances.
        # TODO: Don't run this plugin on wrong instances.
        # This plugin should run only on review product type
        # with instance node of opengl type.
        if ropnode.type().name() != "opengl":
            self.log.debug("Skipping OpenGl extraction. Rop node {} "
                           "is not an OpenGl node.".format(ropnode.path()))
            return

        output = ropnode.evalParm("picture")
        staging_dir = os.path.normpath(os.path.dirname(output))
        instance.data["stagingDir"] = staging_dir
        file_name = os.path.basename(output)

        self.log.info("Extracting '%s' to '%s'" % (file_name,
                                                   staging_dir))

        render_rop(ropnode)

        output = instance.data["frames"]

        tags = ["review"]
        if not instance.data.get("keepImages"):
            tags.append("delete")

        representation = {
            "name": instance.data["imageFormat"],
            "ext": instance.data["imageFormat"],
            "files": output,
            "stagingDir": staging_dir,
            "frameStart": instance.data["frameStartHandle"],
            "frameEnd": instance.data["frameEndHandle"],
            "tags": tags,
            "preview": True,
            "camera_name": instance.data.get("review_camera")
        }

        if ropnode.evalParm("colorcorrect") == 2:  # OpenColorIO enabled
            colorspace = ropnode.evalParm("ociocolorspace")
            # inject colorspace data
            self.set_representation_colorspace(
                representation, instance.context,
                colorspace=colorspace
            )

        if "representations" not in instance.data:
            instance.data["representations"] = []
        instance.data["representations"].append(representation)
