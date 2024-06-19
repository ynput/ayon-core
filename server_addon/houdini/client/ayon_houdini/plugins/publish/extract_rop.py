import os
import hou

import pyblish.api

from ayon_core.pipeline import publish
from ayon_houdini.api import plugin
from ayon_houdini.api.lib import render_rop, get_output_parameter, splitext


class ExtractROP(plugin.HoudiniExtractorPlugin):
    """Generic Extractor for any ROP node."""
    label = "Extract ROP"
    order = pyblish.api.ExtractorOrder

    families = ["abc", "camera", "bgeo", "pointcache", "fbx", "imagesequence",
                "vdbcache", "ass", "redshiftproxy", "mantraifd"]
    targets = ["local", "remote"]

    def process(self, instance: pyblish.api.Instance):
        if instance.data.get("farm"):
            self.log.debug("Should be processed on farm, skipping.")
            return

        rop_node = hou.node(instance.data["instance_node"])

        parm = get_output_parameter(rop_node)
        filepath = parm.eval()
        staging_dir = os.path.dirname(filepath)
        _, ext = splitext(
            filepath, allowed_multidot_extensions=[
                ".ass.gz", ".bgeo.sc", ".bgeo.gz",
                ".bgeo.lzma", ".bgeo.bz2"]
        )

        render_rop(rop_node)
        self.validate_expected_frames(instance, staging_dir)

        # In some cases representation name is not the the extension
        # TODO: Preferably we remove this very specific naming
        product_type = instance.data["productType"]
        name = {
            "bgeo": "bgeo",
            "rs": "rs",
            "ass": "ass",
        }.get(product_type, ext)

        representation = {
            "name": name,
            "ext": ext,
            "files": instance.data["frames"],
            "stagingDir": staging_dir,
            "frameStart": instance.data["frameStartHandle"],
            "frameEnd": instance.data["frameEndHandle"],
        }
        representation = self.update_representation_data(instance,
                                                         representation)
        instance.data.setdefault("representations", []).append(representation)
        instance.data["stagingDir"] = staging_dir

    def validate_expected_frames(self, instance, staging_dir):
        """
        Validate all expected files in `instance.data["frames"]` exist in
        the staging directory.
        """
        filenames = instance.data["frames"]
        if isinstance(filenames, str):
            # Single frame
            filenames = [filenames]

        missing_filenames = []
        for filename in filenames:
            path = os.path.join(staging_dir, filename)
            if not os.path.isfile(path):
                missing_filenames.append(filename)
        if missing_filenames:
            raise RuntimeError(f"Missing frames: {missing_filenames}")

    def update_representation_data(self,
                                   instance: pyblish.api.Instance,
                                   representation: dict):
        """Allow subclass to override the representation data in-place"""
        pass


class ExtractOpenGL(ExtractROP,
                    publish.ColormanagedPyblishPluginMixin):

    order = pyblish.api.ExtractorOrder - 0.01
    label = "Extract OpenGL"
    families = ["review"]

    def process(self, instance):
        # This plugin is triggered when marking render as reviewable.
        # Therefore, this plugin will run over wrong instances.
        # TODO: Don't run this plugin on wrong instances.
        # This plugin should run only on review product type
        # with instance node of opengl type.
        instance_node = instance.data.get("instance_node")
        if not instance_node:
            self.log.debug("Skipping instance without instance node.")
            return

        rop_node = hou.node(instance_node)
        if rop_node.type().name() != "opengl":
            self.log.debug("Skipping OpenGl extraction. Rop node {} "
                           "is not an OpenGl node.".format(rop_node.path()))
            return

        super(ExtractOpenGL, self).process(instance)

    def update_representation_data(self,
                                   instance: pyblish.api.Instance,
                                   representation: dict):

        tags = ["review"]
        if not instance.data.get("keepImages"):
            tags.append("delete")

        representation.update({
            # TODO: Avoid this override?
            "name": instance.data["imageFormat"],
            "ext": instance.data["imageFormat"],

            "tags": tags,
            "preview": True,
            "camera_name": instance.data.get("review_camera")
        })
        return representation


class ExtractComposite(ExtractROP,
                       publish.ColormanagedPyblishPluginMixin):

    label = "Extract Composite (Image Sequence)"
    families = ["imagesequence"]

    def update_representation_data(self,
                                   instance: pyblish.api.Instance,
                                   representation: dict):

        if representation["ext"].lower() != "exr":
            return

        # Inject colorspace with 'scene_linear' as that's the
        # default Houdini working colorspace and all extracted
        # OpenEXR images should be in that colorspace.
        # https://www.sidefx.com/docs/houdini/render/linear.html#image-formats
        self.set_representation_colorspace(
            representation, instance.context,
            colorspace="scene_linear"
        )
