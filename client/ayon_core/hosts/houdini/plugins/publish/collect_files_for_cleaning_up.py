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
        "vdbcache",
        "redshift_rop"
    ]
    label = "Collect Files For Cleaning Up"

    def process(self, instance):

        import hou

        node = hou.node(instance.data.get("instance_node", ""))
        if not node:
            self.log.debug("Skipping Collector. Instance has no instance_node")
            return
        
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
            files = [os.path.join(staging_dir, frames)]
        else:
            files = [os.path.join(staging_dir, f) for f in frames]

        # Render Products
        expectedFiles = instance.data.get("expectedFiles", [])
        for aovs in expectedFiles:
            # aovs.values() is a list of lists
            files.extend(sum(aovs.values(), []))

        # Intermediate exported render files.
        # TODO 1:For products with split render enabled,
        #   We need to calculate all exported frames. as.
        #   `ifdFile` should be a list of files.
        # TODO 2: For products like Karma,
        #   Karma has more intermediate files 
        #   e.g. USD and checkpoint
        ifdFile = instance.data.get("ifdFile")
        if self.intermediate_exported_render and ifdFile:
            files.append(ifdFile)
        
        # Non Render Products with no frames
        if not files:
            files.append(filepath)

        self.log.debug("Add directories to 'cleanupEmptyDir': {}".format(staging_dir))
        instance.context.data["cleanupEmptyDirs"].append(staging_dir)
        
        self.log.debug("Add files to 'cleanupFullPaths': {}".format(files))
        instance.context.data["cleanupFullPaths"] += files
