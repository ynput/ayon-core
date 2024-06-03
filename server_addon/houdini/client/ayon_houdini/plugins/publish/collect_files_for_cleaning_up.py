import pyblish.api
import os
import re
from ayon_core.pipeline import AYONPyblishPluginMixin
from ayon_houdini.api import lib


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
    intermediate_exported_render = False

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
        # Products with frames
        frames = instance.data.get("frames", [])
        staging_dir, _ = os.path.split(filepath)
        if isinstance(frames, str):
            files = [os.path.join(staging_dir, frames)]
        else:
            files = [os.path.join(staging_dir, f) for f in frames]

        # Farm Products with expected files
        expectedFiles = instance.data.get("expectedFiles", [])
        for aovs in expectedFiles:
            # aovs.values() is a list of lists
            files.extend(sum(aovs.values(), []))

        # Intermediate exported render files.
        # TODO : Clean up intermediate files of Karma product type.
        #        as "ifdFile" works for other render product types only.
        ifdFile = instance.data.get("ifdFile")
        if self.intermediate_exported_render and ifdFile:
            start_frame = instance.data.get("frameStartHandle", None)
            end_frame = instance.data.get("frameEndHandle", None)

            ifd_files = self._get_ifd_file_list(ifdFile,
                                                start_frame, end_frame)
            files.extend(ifd_files)

        # Products with single output file/frame
        if not files:
            files.append(filepath)

        self.log.debug("Add directories to 'cleanupEmptyDir': {}".format(staging_dir))
        instance.context.data["cleanupEmptyDirs"].append(staging_dir)

        self.log.debug("Add files to 'cleanupFullPaths': {}".format(files))
        instance.context.data["cleanupFullPaths"] += files

    @staticmethod
    def _get_ifd_file_list(ifdFile, start_frame, end_frame):

        file_name = os.path.basename(ifdFile)
        parent_path = os.path.dirname(ifdFile)

        pattern = r"\w+\.(0+).\w+"  # It's always (0000)
        match = re.match(pattern, file_name)

        if match and start_frame is not None:

            # Check if frames are bigger than 1 (file collection)
            # override the result
            if end_frame - start_frame > 0:
                result = lib.create_file_list(
                    match, int(start_frame), int(end_frame)
                )
                result = [
                    os.path.join(parent_path, r).replace("\\", "/")
                    for r in result
                ]

                return result

        return []
