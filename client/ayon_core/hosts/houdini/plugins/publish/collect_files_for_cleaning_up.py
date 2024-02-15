import pyblish.api
import os
from ayon_core.pipeline import AYONPyblishPluginMixin


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
        filepath = self.get_filepath(node)

        if not filepath:
            self.log.warning("No filepath value to collect.")
            return
    
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

    def get_filepath(self, node):
        # Get sop path
        node_type = node.type().name()
        filepath = None
        if node_type == "geometry":
            filepath = node.evalParm("sopoutput")

        elif node_type == "comp":
            filepath = node.evalParm("copoutput")

        elif node_type == "alembic":
            filepath = node.evalParm("filename")

        elif node_type == "ifd":
            if node.evalParm("soho_outputmode"):
                filepath = node.evalParm("soho_diskfile")
            else:
                filepath = node.evalParm("vm_picture")    

        elif node_type == "Redshift_Proxy_Output":
            filepath = node.evalParm("RS_archive_file")
            
        elif node_type == "Redshift_ROP":
            filepath = node.evalParm("RS_outputFileNamePrefix")

        elif node_type == "opengl":
            filepath = node.evalParm("picture")

        elif node_type == "filmboxfbx":
            filepath = node.evalParm("sopoutput")

        elif node_type == "usd":
            filepath = node.evalParm("lopoutput")

        elif node_type == "karma":
            filepath = node.evalParm("picture")
        
        elif node_type == "arnold":
            if node.evalParm("ar_ass_export_enable"):
                filepath = node.evalParm("ar_ass_file")
            else:
                filepath = node.evalParm("ar_picture") 
        
        elif node_type == "vray_renderer":
            filepath = node.evalParm("SettingsOutput_img_file_path")
        
        else:
            self.log.debug(
                "ROP node type '{}' is not supported for cleaning up."
                .format(node_type)
            )
         
        return filepath