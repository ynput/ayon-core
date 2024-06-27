import os

import clique
import pyblish.api
from ayon_core.pipeline import AYONPyblishPluginMixin
from ayon_houdini.api import plugin


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

        files: list[os.PathLike] = []
        staging_dirs: list[os.PathLike] = []

        expected_files = instance.data.get("expectedFiles", [])

        # Prefer 'expectedFiles' over 'frames' because it usually contains
        # more output files than just a single file or single sequence of files.
        if expected_files:
            # Products with expected files
            # This can be Render products or submitted cache to farm.
            for expected in expected_files:
                # expected.values() is a list of lists
                for output_files in expected.values():
                    staging_dir, _ = os.path.split(output_files[0])
                    if staging_dir not in staging_dirs:
                        staging_dirs.append(staging_dir)
                    files.extend(output_files)
        else:
            # Products with frames or single file.

            frames = instance.data.get("frames")
            if frames is None:
                self.log.warning(
                    f"No frames data found on instance {instance}"
                    ". Skipping collection for caching on farm..."
                )
                return

            staging_dir = instance.data.get("stagingDir")
            staging_dirs.append(staging_dir)

            if isinstance(frames, str):
                # single file.
                files.append(f"{staging_dir}/{frames}")
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
            staging_dirs.append(os.path.dirname(ifd_file))
            files.extend(ifd_files)

        self.log.debug(
            f"Add directories to 'cleanupEmptyDir': {staging_dirs}")
        instance.context.data["cleanupEmptyDirs"].extend(staging_dirs)

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
