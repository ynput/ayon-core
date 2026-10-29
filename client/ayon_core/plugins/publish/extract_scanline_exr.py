# -*- coding: utf-8 -*-
"""Convert tiled EXRs to scanline EXRs using the OIIO tool."""
import os
import uuid

import pyblish.api

from ayon_core.lib import (
    run_subprocess,
    get_oiio_tool_args,
    ToolNotFoundError,
)
from ayon_core.pipeline import PublishError


class ExtractScanlineExr(pyblish.api.InstancePlugin):
    """Convert tiled EXRs to scanline using OIIO tool.

    Only EXR representations tagged ``toScanline`` are processed; the
    original files are replaced in place, so the file list of the
    representation does not change.
    """

    label = "Extract Scanline EXR"
    hosts = ["shell"]
    order = pyblish.api.ExtractorOrder
    families = ["imagesequence", "render", "render2d", "source"]

    def process(self, instance):
        """Plugin entry point."""
        # get representation and loop them
        representations = instance.data["representations"]

        for repre in representations:
            self.log.debug(
                "Processing representation {}".format(repre.get("name")))
            tags = repre.get("tags", [])
            if "toScanline" not in tags:
                self.log.debug(" - missing toScanline tag")
                continue

            # run only on exrs
            if str(repre.get("ext", "")).lower() != "exr":
                self.log.debug("- not EXR files")
                continue

            staging_dir = repre.get("stagingDir")
            if not staging_dir:
                self.log.debug(
                    "Staging directory not found for representation"
                )
                continue
            stagingdir = os.path.normpath(staging_dir)

            if not isinstance(repre["files"], (list, tuple)):
                input_files = [repre["files"]]
                self.log.debug("We have a single frame")
            else:
                input_files = repre["files"]
                self.log.debug("We have a sequence")

            try:
                oiio_tool_args = get_oiio_tool_args("oiiotool")
            except ToolNotFoundError:
                self.log.error("OIIO tool not found.")
                raise PublishError("OIIO tool not found")

            self._convert_to_scanline(input_files, stagingdir, oiio_tool_args)
            if any(
                other is not repre and other.get("name") == "exr"
                for other in representations
            ):
                self.log.warning(
                    "Another representation is already named 'exr'; the"
                    " converted representation may clash with it."
                )
            repre['name'] = "exr"
            if "toScanline" in tags:
                tags.remove("toScanline")

    def _convert_to_scanline(
            self, input_files, stagingdir, oiio_tool_args) -> None:
        """Convert the files to scanline, keeping sources intact on error.

        Two phases: every source file is converted to a unique temporary
        output next to it, and only after all files were converted
        successfully are the outputs swapped over the original files.
        Any failure removes the temporary outputs and leaves all source
        files untouched.

        Only flat/tiled EXRs are supported; deep or multipart EXRs can
        make oiiotool fail and are reported as a conversion error.

        A failure in one representation aborts the instance: the
        representations converted before it stay converted (they are valid
        scanline EXRs), the failing and later ones are left untouched.

        Each temporary output gets a unique name next to its source, so a
        retried publish cannot collide with leftovers of an earlier run.

        Args:
            input_files (list): The names of the input EXR files.
            stagingdir (str): The directory where the input file is located.
            oiio_tool_args (list): The command-line arguments for the
                OIIO tool.
        """
        pending_files = []

        for file in input_files:
            source_path = os.path.join(stagingdir, file)
            if not os.path.isfile(source_path):
                raise PublishError(
                    f"File to convert does not exist: {source_path}"
                )
            stem, extension = os.path.splitext(os.path.basename(file))
            extension = extension.lower() or ".exr"
            temp_path = os.path.join(
                os.path.dirname(source_path),
                f".{stem}.{uuid.uuid4().hex}{extension}")
            oiio_cmd = oiio_tool_args + [
                source_path, "--scanline", "-o",
                temp_path,
            ]

            self.log.debug(f"running: {' '.join(oiio_cmd)}")
            try:
                run_subprocess(oiio_cmd, logger=self.log)
            except RuntimeError as exc:
                raise PublishError(
                    f"oiiotool failed to convert '{source_path}' "
                    "to scanline."
                ) from exc
            # Register the temporary output before validating it, so the
            # finally block removes it when the conversion produced
            # nothing or a zero-byte file.
            pending_files.append((source_path, temp_path))

            if (
                not os.path.isfile(temp_path)
                or os.path.getsize(temp_path) == 0
            ):
                raise PublishError(
                    f"Failed to convert file to scanline EXR:"
                    f" {source_path}"
                )

        # Every file converted: swap outputs over the sources.
        while pending_files:
            source_path, temp_path = pending_files[0]
            try:
                os.replace(temp_path, source_path)
            except OSError as e:
                raise PublishError(
                    "Unable to replace original file with scanline EXR:"
                    f" {source_path}. Error: {e}"
                ) from e
            pending_files.pop(0)

        for _source_path, temp_path in pending_files:
            if not os.path.exists(temp_path):
                continue
            try:
                os.remove(temp_path)
            except OSError:
                self.log.warning(
                    f"Failed to remove temporary file: {temp_path}"
                )
