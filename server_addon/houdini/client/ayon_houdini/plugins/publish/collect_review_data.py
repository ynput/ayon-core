import hou
import pyblish.api
from ayon_houdini.api import plugin


class CollectHoudiniReviewData(plugin.HoudiniInstancePlugin):
    """Collect Review Data."""

    label = "Collect Review Data"
    # This specific order value is used so that
    # this plugin runs after CollectRopFrameRange
    # Also after CollectLocalRenderInstances
    order = pyblish.api.CollectorOrder + 0.13
    families = ["review"]

    def process(self, instance):

        # This fixes the burnin having the incorrect start/end timestamps
        # because without this it would take it from the context instead
        # which isn't the actual frame range that this instance renders.
        instance.data["handleStart"] = 0
        instance.data["handleEnd"] = 0
        instance.data["fps"] = instance.context.data["fps"]

        # Enable ftrack functionality
        instance.data.setdefault("families", []).append('ftrack')

        # Get the camera from the rop node to collect the focal length
        ropnode_path = instance.data["instance_node"]
        ropnode = hou.node(ropnode_path)

        # Get camera based on the instance_node type.
        camera_path = self._get_camera_path(ropnode)
        camera_node = hou.node(camera_path)
        if not camera_node:
            self.log.warning("No valid camera node found on review node: "
                             "{}".format(camera_path))
            return

        # Collect focal length.
        focal_length_parm = camera_node.parm("focal")
        if not focal_length_parm:
            self.log.warning("No 'focal' (focal length) parameter found on "
                             "camera: {}".format(camera_path))
            return

        if focal_length_parm.isTimeDependent():
            start = instance.data["frameStartHandle"]
            end = instance.data["frameEndHandle"] + 1
            focal_length = [
                focal_length_parm.evalAsFloatAtFrame(t)
                for t in range(int(start), int(end))
            ]
        else:
            focal_length = focal_length_parm.evalAsFloat()

        # Store focal length in `burninDataMembers`
        burnin_members = instance.data.setdefault("burninDataMembers", {})
        burnin_members["focalLength"] = focal_length

    def _get_camera_path(self, ropnode):
        """Get the camera path associated with the given rop node.

        This function evaluates the camera parameter according to the
        type of the given rop node.

        Returns:
            Union[str, None]: Camera path or None.

            This function can return empty string if the camera
            path is empty i.e. no camera path.
        """

        if ropnode.type().name() in {
            "opengl", "karma", "ifd", "arnold"
        }:
            return ropnode.parm("camera").eval()

        elif ropnode.type().name() == "Redshift_ROP":
            return ropnode.parm("RS_renderCamera").eval()

        elif ropnode.type().name() == "vray_renderer":
            return ropnode.parm("render_camera").eval()

        return None
