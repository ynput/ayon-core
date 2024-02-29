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
    
        staging_dir, _ = os.path.split(filepath)
        files = instance.data.get("frames", [])
        if files: 
            files = ["{}/{}".format(staging_dir, f) for f in files]
        else:
            files = [filepath]

        self.log.debug("Add directories to 'cleanupEmptyDir': {}".format(staging_dir))
        instance.context.data["cleanupEmptyDirs"].append(staging_dir)
        
        self.log.debug("Add files to 'cleanupFullPaths': {}".format(files))
        instance.context.data["cleanupFullPaths"] += files
