import pyblish.api
import os
from ayon_core.pipeline import AYONPyblishPluginMixin
from ayon_core.hosts.houdini.api import lib


class CollectFilesForCleaningUp(pyblish.api.InstancePlugin,
                                AYONPyblishPluginMixin):
    """Collect Files For Cleaning Up.
    
    This collector collects output files
    and adds them to file remove list.

    CAUTION:
        This collector deletes the exported files and
          deletes the parent folder if it was empty.
        Artists are free to change the file path in the ROP node.
    """

    order = pyblish.api.CollectorOrder + 0.2  # it should run after CollectFrames

    hosts = ["houdini"]
    families = [
        "camera",
        "ass",
        "pointcache",
        "imagesequence",
        "mantraifd",
        "redshiftproxy",
        "review",
        "staticMesh",
        "usd",
        "vdbcache"
    ]
    label = "Collect Files For Cleaning Up"

    def process(self, instance):

        import hou

        node = hou.node(instance.data["instance_node"])
        output_parm = lib.get_output_parameter(node)
        if not output_parm:
            self.log.debug("ROP node type '{}' is not supported for cleaning up."
                           .format(node.type().name()))
            return
        
        filepath = output_parm.eval()
        if not filepath:
            self.log.warning("No filepath value to collect.")
            return

        files = []
        # Non Render Products with frames
        frames = instance.data.get("frames", [])
        staging_dir, _ = os.path.split(filepath)
        if isinstance(frames, str):
            files = ["{}/{}".format(staging_dir, frames)]
        else:
            files = ["{}/{}".format(staging_dir, f) for f in frames]

        # Render Products
        expectedFiles = instance.data.get("expectedFiles", [])
        for aov in expectedFiles:
            for v in aov.values():
                files += v

        # Render Intermediate files.
        # This doesn't cover all intermediate render products.
        # E.g. Karma's USD and checkpoint.
        # For some reason it's one file with $F4 evaluated as 0000
        # So, we need to get all the frames.
        ifdFile = instance.data.get("ifdFile")
        if self.include_intermediate_files and ifdFile:
            files += [ifdFile]
        
        # Non Render Products with no frames
        if not files:
            files = [filepath]

        self.log.debug("Add directories to 'cleanupEmptyDir': {}".format(staging_dir))
        instance.context.data["cleanupEmptyDirs"].append(staging_dir)
        
        self.log.debug("Add files to 'cleanupFullPaths': {}".format(files))
        instance.context.data["cleanupFullPaths"] += files
