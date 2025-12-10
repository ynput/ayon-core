"""Create instance thumbnail from "thumbnailSource" on 'instance.data'.

Output is new representation with "thumbnail" name on instance. If instance
already have such representation the process is skipped.

This way a collector can point to a file from which should be thumbnail
generated. This is different approach then what global plugin for thumbnails
does. The global plugin has specific logic which does not support

Todos:
    No size handling. Size of input is used for output thumbnail which can
        cause issues.
"""

import os
from dataclasses import dataclass, field, fields
import tempfile
from typing import Dict, Any, List, Tuple, Optional

import pyblish.api
from ayon_core.lib import (
    get_ffmpeg_tool_args,
    get_oiio_tool_args,
    is_oiio_supported,

    run_subprocess,
    get_rescaled_command_arguments,
    filter_profiles,
)


class ExtractThumbnailFromSource(pyblish.api.InstancePlugin):
    """Create jpg thumbnail for instance based on 'thumbnailSource'.

    Thumbnail source must be a single image or video filepath.
    """

    label = "Extract Thumbnail (from source)"
    # Before 'ExtractThumbnail' in global plugins
    order = pyblish.api.ExtractorOrder + 0.48

    # Settings
    target_size = {"type": "source", "resize": {"width": 1920, "height": 1080}}
    background_color = (0, 0, 0, 0.0)


    def process(self, instance: pyblish.api.Instance):
        context_thumbnail_path = self._create_context_thumbnail(
            instance.context
        )
        if context_thumbnail_path:
            instance.context.data["thumbnailPath"] = context_thumbnail_path

        thumbnail_source = instance.data.get("thumbnailSource")
        if not thumbnail_source:
            self.log.debug("Thumbnail source not filled. Skipping.")
            return

        # Check if already has thumbnail created
        if self._instance_has_thumbnail(instance):
            self.log.debug("Thumbnail representation already present.")
            return

        dst_filepath = self._create_thumbnail(
            instance.context, thumbnail_source
        )
        if not dst_filepath:
            return

        dst_staging, dst_filename = os.path.split(dst_filepath)
        new_repre = {
            "name": "thumbnail",
            "ext": "jpg",
            "files": dst_filename,
            "stagingDir": dst_staging,
            "thumbnail": True,
            "tags": ["thumbnail"],
            "outputName": "thumbnail",
        }

        new_repre["tags"].append("delete")

        # adding representation
        self.log.debug(
            "Adding thumbnail representation: {}".format(new_repre)
        )
        instance.data["representations"].append(new_repre)
        instance.data["thumbnailPath"] = dst_filepath

    def _create_thumbnail(
        self,
        context: pyblish.api.Context,
        thumbnail_source: str,
    ) -> Optional[str]:
        if not thumbnail_source:
            self.log.debug("Thumbnail source not filled. Skipping.")
            return

        if not os.path.exists(thumbnail_source):
            self.log.debug((
                "Thumbnail source is set but file was not found {}. Skipping."
            ).format(thumbnail_source))
            return

        # Create temp directory for thumbnail
        # - this is to avoid "override" of source file
        dst_staging = tempfile.mkdtemp(prefix="pyblish_tmp_")
        self.log.debug(
            "Create temp directory {} for thumbnail".format(dst_staging)
        )
        # Store new staging to cleanup paths
        context.data["cleanupFullPaths"].append(dst_staging)

        thumbnail_created = False
        oiio_supported = is_oiio_supported()

        self.log.debug("Thumbnail source: {}".format(thumbnail_source))
        src_basename = os.path.basename(thumbnail_source)
        dst_filename = os.path.splitext(src_basename)[0] + "_thumb.jpg"
        full_output_path = os.path.join(dst_staging, dst_filename)

        if oiio_supported:
            self.log.debug("Trying to convert with OIIO")
            # If the input can read by OIIO then use OIIO method for
            # conversion otherwise use ffmpeg
            thumbnail_created = self.create_thumbnail_oiio(
                thumbnail_source, full_output_path
            )

        # Try to use FFMPEG if OIIO is not supported or for cases when
        #    oiiotool isn't available
        if not thumbnail_created:
            if oiio_supported:
                self.log.info(
                    "Converting with FFMPEG because input"
                    " can't be read by OIIO."
                )

            thumbnail_created = self.create_thumbnail_ffmpeg(
                thumbnail_source, full_output_path
            )

        # Skip representation and try next one if  wasn't created
        if thumbnail_created:
            return full_output_path

        self.log.warning("Thumbnail has not been created.")

    def _instance_has_thumbnail(self, instance: pyblish.api.Instance) -> bool:
        if "representations" not in instance.data:
            self.log.warning(
                "Instance does not have 'representations' key filled"
            )
            instance.data["representations"] = []

        for repre in instance.data["representations"]:
            if repre["name"] == "thumbnail":
                return True
        return False

    def create_thumbnail_oiio(
        self,
        src_path: str,
        dst_path: str,
    ) -> bool:
        self.log.debug("Outputting thumbnail with OIIO: {}".format(dst_path))
        resolution_arg = self._get_resolution_arg(
            "oiiotool", src_path
        )
        oiio_cmd = get_oiio_tool_args("oiiotool", "-a", src_path)
        if resolution_arg:
            # resize must be before -o
            oiio_cmd.extend(resolution_arg)
        else:
            # resize provides own -ch, must be only one
            oiio_cmd.extend(["--ch", "R,G,B"])

        oiio_cmd.extend(["-o", dst_path])
        self.log.debug("Running: {}".format(" ".join(oiio_cmd)))
        try:
            run_subprocess(oiio_cmd, logger=self.log)
            return True
        except Exception:
            self.log.warning(
                "Failed to create thumbnail using oiiotool",
                exc_info=True
            )
            return False

    def create_thumbnail_ffmpeg(
        self,
        src_path: str,
        dst_path: str,
    ) -> bool:
        resolution_arg = self._get_resolution_arg(
            "ffmpeg", src_path
        )

        max_int = str(2147483647)
        ffmpeg_cmd = get_ffmpeg_tool_args(
            "ffmpeg",
            "-y",
            "-analyzeduration", max_int,
            "-probesize", max_int,
            "-i", src_path,
            "-frames:v", "1",
        )

        if resolution_arg:
            ffmpeg_cmd.extend(resolution_arg)

        # possible resize must be before output args
        ffmpeg_cmd.append(dst_path)

        self.log.debug("Running: {}".format(" ".join(ffmpeg_cmd)))
        try:
            run_subprocess(ffmpeg_cmd, logger=self.log)
            return True
        except Exception:
            self.log.warning(
                "Failed to create thumbnail using ffmpeg",
                exc_info=True
            )
            return False

    def _create_context_thumbnail(
        self,
        context: pyblish.api.Context,
    ) -> Optional[str]:
        hasContextThumbnail = "thumbnailPath" in context.data
        if hasContextThumbnail:
            return

        thumbnail_source = context.data.get("thumbnailSource")
        thumbnail_path = self._create_thumbnail(
            context, thumbnail_source
        )
        return thumbnail_path

    def _get_resolution_arg(
        self,
        application: str,
        input_path: str,
    ) -> List[str]:
        # get settings
        if self.target_size["type"] == "source":
            return []

        resize = self.target_size["resize"]
        target_width = resize["width"]
        target_height = resize["height"]

        # form arg string per application
        return get_rescaled_command_arguments(
            application,
            input_path,
            target_width,
            target_height,
            bg_color=self.background_color,
            log=self.log,
        )
