import os

import clique
import pyblish.api
from ayon_core.pipeline import AYONPyblishPluginMixin
from ayon_houdini.api import lib, plugin


class CollectFilesForCleaningUp(plugin.HoudiniInstancePlugin,
                                AYONPyblishPluginMixin):
    """Collect Files For Cleaning Up.

    This collector collects output files
    and adds them to file remove list.

    CAUTION:
        This collector registers exported files and
          the parent folder (if it was empty) for deletion
          in `ExplicitCleanUp` plug-in.
        Artists are free to change the file path in the ROP node.
    """

    # It should run after CollectFrames and Collect Render plugins,
    # and before CollectLocalRenderInstances.
    order = pyblish.api.CollectorOrder + 0.115

    hosts = ["houdini"]
    families = ["*"]
    label = "Collect Files For Cleaning Up"
    intermediate_exported_render = False

    def process(self, instance):
        import hou  # noqa: E402

        node = hou.node(instance.data.get("instance_node", ""))
        if not node:
            self.log.debug(
                "Skipping Collector. Instance has no instance_node")
            return

        output_parm = lib.get_output_parameter(node)
        if not output_parm:
            self.log.debug(
                f"ROP node type '{node.type().name()}' is not "
                "supported for cleaning up.")
            return

        filepath = output_parm.eval()
        if not filepath:
            self.log.warning("No filepath value to collect.")
            return

        files = []
        staging_dir, _ = os.path.split(filepath)

        expected_files = instance.data.get("expectedFiles", [])

        # 'expectedFiles' are preferred over 'frames'
        if expected_files:
            # Products with expected files
            # This can be Render products or submitted cache to farm.
            for expected in expected_files:
                # expected.values() is a list of lists
                for output_files in expected.values():
                    files.extend(output_files)
        else:
            # Products with frames or single file.
            frames = instance.data.get("frames", "")
            if isinstance(frames, str):
                # single file.
                files.append(filepath)
            else:
                # list of frame.
                files.extend(
                    [f"{staging_dir}/{frame}" for frame in frames]
                )

        # Intermediate exported render files.
        # Note: This only takes effect when setting render target to
        #       "Farm Rendering - Split export & render jobs"
        #       as it's the only case where "ifdFile" exists in instance data.
        # TODO : Clean up intermediate files of Karma product type.
        #        as "ifdFile" works for other render product types only.
        ifd_file = instance.data.get("ifdFile")
        if self.intermediate_exported_render and ifd_file:
            start_frame = instance.data["frameStartHandle"]
            end_frame = instance.data["frameEndHandle"]
            ifd_files = self._get_ifd_file_list(ifd_file,
                                                start_frame, end_frame)
            files.extend(ifd_files)

        self.log.debug(
            f"Add directories to 'cleanupEmptyDir': {staging_dir}")
        instance.context.data["cleanupEmptyDirs"].append(staging_dir)

        self.log.debug("Add files to 'cleanupFullPaths': {}".format(files))
        instance.context.data["cleanupFullPaths"].extend(files)

    def _get_ifd_file_list(self, ifd_file, start_frame, end_frame):

        file_name = os.path.basename(ifd_file)
        parent_path = os.path.dirname(ifd_file)

        # Compute frames list
        frame_collection, _ = clique.assemble(
            [file_name],
            patterns=[clique.PATTERNS["frames"]],
            minimum_items=1
        )

        # It's always expected to be one collection.
        frame_collection = frame_collection[0]
        frame_collection.indexes.clear()
        frame_collection.indexes.update(
            list(range(start_frame, (end_frame + 1))))

        return [f"{parent_path}/{frame}" for frame in frame_collection]
