import os
import shutil
import hou
from intspan import intspan
import pyblish.api
from ayon_core.lib import collect_frames
from ayon_houdini.api import plugin, lib


class ExtractLastPublished(plugin.HoudiniExtractorPlugin):
    """
    Generic Extractor that copies files from last published
    to staging directory.
    It works only if instance data includes "last_version_published_files"
    and there are frames to fix.

    The files from last published are base of files which will be extended/fixed for specific
    frames.
    """

    order = pyblish.api.ExtractorOrder - 0.1
    label = "Extract Last Published"
    families = ["*"]

    def process(self, instance):
        frames_to_fix = instance.data.get("frames_to_fix")
        last_published = instance.data.get("last_version_published_files")
        if not (frames_to_fix or last_published):
            self.log.debug("Nothing to copy.")
            return

        # Get a list of expected filenames
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

        expected_filenames = []
        staging_dir, _ = os.path.split(filepath)
        expectedFiles = instance.data.get("expectedFiles", [])

        # 'expectedFiles' are preferred over 'frames'
        if expectedFiles:
            # Products with expected files
            # This can be Render products or submitted cache to farm.
            for expected in expectedFiles:
                # expected.values() is a list of lists
                expected_filenames.extend(sum(expected.values(), []))
        else:
            # Products with frames or single file.
            frames = instance.data.get("frames", "")
            if isinstance(frames, str):
                # single file.
                expected_filenames.append(filepath)
            else:
                # list of frame.
                expected_filenames.extend(
                    ["{}/{}".format(staging_dir, f) for f in frames]
                )

        if not os.path.exists(staging_dir):
            os.makedirs(staging_dir)

        anatomy = instance.context.data["anatomy"]
        last_published_and_frames = collect_frames(last_published)

        expected_and_frames = collect_frames(expected_filenames)
        frames_and_expected = {v: k for k, v in expected_and_frames.items()}
        frames_to_fix = intspan(frames_to_fix)

        for file_path, frame in last_published_and_frames.items():
            file_path = anatomy.fill_root(file_path)
            if not os.path.exists(file_path):
                continue
            target_file_name = frames_and_expected.get(frame)
            if not target_file_name:
                continue

            out_path = os.path.join(staging_dir, target_file_name)

            # Copy only the frames that we won't render.
            if int(frame) not in frames_to_fix:
                self.log.debug("Copying '{}' -> '{}'".format(file_path, out_path))
                shutil.copy(file_path, out_path)
