import pyblish.api
import os
from ayon_core.pipeline import AYONPyblishPluginMixin


class CollectStagingDirsForCleaningUp(pyblish.api.InstancePlugin,
                                      AYONPyblishPluginMixin):
    """Collect Staging Directories For Cleaning Up.
    
    This collector collects staging directories
    and adds them to file remove list.

    CAUTION:
        This collector deletes the parent folder of the exported files.
        It works fine with the default filepaths in the creators.
        Artist should be aware with that fact so they take care when 
          changing the file path in the ROP node.
        Developers should be aware when changing the filepath pattern
          in creator plugins.
    """

    order = pyblish.api.CollectorOrder

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
    ]
    label = "Collect Staging Directories For Cleaning Up"

    def process(self, instance):

        import hou

        node = hou.node(instance.data["instance_node"])

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
            filepath = node.evalParm("vm_picture")
            # vm_picture is empty when mantra node is 
            #   used to export .ifd files only.
            if not filepath:
                filepath = node.evalParm("soho_diskfile")

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
            filepath = node.evalParm("ar_picture")
            # ar_picture is empty when arnold node is 
            #   used to export .ass files only.
            if not filepath:
                filepath = node.evalParm("ar_ass_file")
        
        elif node_type == "vray_renderer":
            filepath = node.evalParm("SettingsOutput_img_file_path")
        
        else:
            self.log.debug(
                "ROP node type '{}' is not supported for cleaning up."
                .format(node_type)
            )
            return

        if not filepath:
            self.log.warning("No filepath value to collect.")
            return
        filepath = os.path.dirname(filepath)
        self.log.debug("Add to clean up list: {}".format(filepath))
        instance.context.data["cleanupFullPaths"].append(filepath)
