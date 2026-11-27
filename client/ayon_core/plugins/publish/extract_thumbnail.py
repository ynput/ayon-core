from __future__ import annotations

import copy
import logging
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TYPE_CHECKING

import pyblish.api
from ayon_core.lib import (
    get_oiio_tool_args,
    get_ffmpeg_tool_args,
    get_ffprobe_data,

    is_oiio_supported,
    get_rescaled_command_arguments,

    path_to_subprocess_arg,
    run_subprocess,
    filter_profiles,
)
from ayon_core.lib.transcoding import (
    MissingRGBAChannelsError,
    oiio_color_convert,
    get_oiio_input_and_channel_args,
    get_oiio_info_for_input,
)
from ayon_core.pipeline.publish.lib import get_default_reviewable_layers
from ayon_core.pipeline.colorspace import get_representation_ocio_config_path

from ayon_core.lib.transcoding import VIDEO_EXTENSIONS, IMAGE_EXTENSIONS

if TYPE_CHECKING:
    from ayon_core.pipeline import Anatomy


class ThumbnailDef:
    """
    Data class representing the full configuration for selected profile

    Any change of controllable fields in Settings must propagate here!
    """
    def __init__(
        self,
        integrate_thumbnail: bool = False,
        target_size: dict[str, Any] | None = None,
        duration_split: float = 0.5,
        oiiotool_defaults: dict[str, str] | None = None,
        ffmpeg_args: dict[str, list[Any]] | None = None,
        background_color: tuple[int, int, int, float] = (0, 0, 0, 0.0)
    ) -> None:
        if target_size is None:
            target_size = {
                "type": "source",
                "resize": {"width": 1920, "height": 1080},
            }

        if oiiotool_defaults is None:
            oiiotool_defaults = {
                "type": "colorspace",
                "colorspace": "color_picking"
            }

        if ffmpeg_args is None:
            ffmpeg_args = {"input": [], "output": []}

        self.integrate_thumbnail: bool = integrate_thumbnail
        self.target_size: dict[str, Any] = target_size
        self.duration_split: float = duration_split
        self.oiiotool_defaults: dict[str, str] = oiiotool_defaults
        self.ffmpeg_args: dict[str, list[Any]] = ffmpeg_args
        # Background color defined as (R, G, B, A) tuple.
        # Note: Use float for alpha channel (0.0 to 1.0).
        self.background_color: tuple[int, int, int, float] = background_color

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ThumbnailDef:
        """
        Creates a ThumbnailDef instance from a dictionary, safely ignoring
        any keys in the dictionary that are not fields in the dataclass.

        Args:
            data (dict[str, Any]): The dictionary containing configuration data

        Returns:
            MediaConfig: A new instance of the dataclass.
        """
        # Get all field names defined in the dataclass
        field_names = {
            "integrate_thumbnail",
            "target_size",
            "duration_split",
            "oiiotool_defaults",
            "ffmpeg_args",
            "background_color",
        }

        # Filter the input dictionary to include only keys matching field names
        filtered_data = {k: v for k, v in data.items() if k in field_names}

        # Unpack the filtered dictionary into the constructor
        return cls(**filtered_data)


class _InstanceLogAdapter(logging.LoggerAdapter):
    """Prefix log messages with the instance label.

    Instances are processed in parallel, the prefix keeps the interleaved
    log messages attributable to an instance.
    """

    def process(
        self, msg: Any, kwargs: dict[str, Any]
    ) -> tuple[str, dict[str, Any]]:
        return f"[{self.extra['label']}] {msg}", kwargs


class _InstanceResult:
    """Thumbnail extraction result of one instance.

    Filled by a worker thread and applied to the instance in the main thread
    once all workers finished.

    Attributes:
        instance (pyblish.api.Instance): Processed instance.
        label (str): Instance label used in logs and error messages.
        log (logging.LoggerAdapter): Logger prefixing the instance label.
        staging_dir (str | None): Created temporary staging directory that
            should be cleaned up after publishing.
        representations (list[dict[str, Any]]): New thumbnail
            representations to add to the instance.
        error (Exception | None): Unexpected error raised during extraction.
    """
    def __init__(
        self, instance: pyblish.api.Instance, logger: logging.Logger
    ) -> None:
        label: str = instance.data.get("label") or instance.data["name"]
        self.instance: pyblish.api.Instance = instance
        self.label: str = label
        self.log: logging.LoggerAdapter = _InstanceLogAdapter(
            logger, {"label": label}
        )
        self.staging_dir: str | None = None
        self.representations: list[dict[str, Any]] = []
        self.error: Exception | None = None


class ExtractThumbnail(pyblish.api.ContextPlugin):
    """Create jpg thumbnail from sequence using ffmpeg

    Instances are processed in parallel in a thread pool because the
    extraction mostly waits on ffprobe, ffmpeg and oiiotool subprocesses.
    Instances are filtered by 'families' and active state the same way as
    pyblish does for an instance plugin.

    Worker threads only compute the thumbnails, the instance and context
    data are modified in the main thread after all workers finished.
    """

    label = "Extract Thumbnail"
    order = pyblish.api.ExtractorOrder + 0.49
    families = [
        "imagesequence", "render", "render2d", "prerender",
        "source", "clip", "take", "online", "image", "editorial_pkg"
    ]
    hosts = [
        "shell",
        "fusion",
        "resolve",
        "traypublisher",
        "substancepainter",
        "substancedesigner",
        "nuke",
        "aftereffects",
        "photoshop",
        "unreal",
        "houdini",
        "batchdelivery",
        "workflow",
    ]
    settings_category = "core"
    enabled = False

    profiles = []

    # Maximum number of instances processed in parallel. With 1 the instances
    #   are processed serially in the main thread.
    max_workers: int = min(8, os.cpu_count() or 1)

    def process(self, context: pyblish.api.Context) -> None:
        results = [
            _InstanceResult(instance, self.log)
            for instance in self._get_instances(context)
        ]
        if not results:
            self.log.debug("No instances to extract thumbnails for.")
            return

        max_workers = min(self.max_workers, len(results))
        if max_workers <= 1:
            for result in results:
                self._process_instance(result)
        else:
            self.log.debug(
                f"Extracting thumbnails for {len(results)} instances"
                f" using {max_workers} workers."
            )
            with ThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix=self.__class__.__name__,
            ) as executor:
                # Consume the iterator to re-raise errors not caught by
                #   the worker function
                list(executor.map(self._process_instance, results))

        # Apply results in the main thread in order of instances
        failed_results = []
        for result in results:
            # Store new staging to cleanup paths, also for failed instances
            if result.staging_dir:
                context.data["cleanupFullPaths"].append(result.staging_dir)

            if result.error is not None:
                failed_results.append(result)
                continue
            self._apply_result(result)

        if failed_results:
            labels = ", ".join(result.label for result in failed_results)
            raise RuntimeError(
                f"Failed to extract thumbnail for instances: {labels}"
            ) from failed_results[0].error

    def _get_instances(
        self, context: pyblish.api.Context
    ) -> list[pyblish.api.Instance]:
        """Get instances to extract thumbnails for.

        Same filtering as pyblish does for an instance plugin, instances with
            matching families that are not disabled for publishing.

        Args:
            context (pyblish.api.Context): Publish context.

        Returns:
            list[pyblish.api.Instance]: Instances to process.

        """
        return [
            instance
            for instance in pyblish.api.instances_by_plugin(context, self)
            if instance.data.get("publish") is not False
        ]

    def _process_instance(self, result: _InstanceResult) -> None:
        """Extract thumbnails for one instance.

        Called from worker threads. Errors are stored to the result so
            the remaining instances can finish.

        Args:
            result (_InstanceResult): Result of the instance to process.

        """
        try:
            self._main_process(result.instance, result, result.log)
        except Exception as exc:
            result.log.error("Failed to extract thumbnail.", exc_info=True)
            result.error = exc

    def _apply_result(self, result: _InstanceResult) -> None:
        """Apply extracted thumbnails to the instance.

        Must be called in the main thread.

        Args:
            result (_InstanceResult): Result of a processed instance.

        """
        instance = result.instance
        for new_repre in result.representations:
            full_output_path = os.path.join(
                new_repre["stagingDir"], new_repre["files"]
            )
            # add thumbnail path to instance data for integrator
            instance_thumb_path = instance.data.get("thumbnailPath")
            if (
                not instance_thumb_path
                or not os.path.isfile(instance_thumb_path)
            ):
                result.log.debug(
                    "Adding thumbnail path to instance data: {}".format(
                        full_output_path
                    )
                )
                instance.data["thumbnailPath"] = full_output_path

            # adding representation
            instance.data["representations"].append(new_repre)

        # Make sure cleanup happens to representations which are having both
        # tags `delete` and `need_thumbnail`
        for repre in tuple(instance.data.get("representations", [])):
            tags = repre.get("tags") or []
            # skip representations which are going to be published on farm
            if "publish_on_farm" in tags:
                continue
            if (
                "delete" in tags
                and "need_thumbnail" in tags
            ):
                result.log.debug(
                    "Removing representation: {}".format(repre)
                )
                instance.data["representations"].remove(repre)

    def _main_process(
        self,
        instance: pyblish.api.Instance,
        result: _InstanceResult,
        log: logging.Logger | logging.LoggerAdapter,
    ) -> None:
        """Extract thumbnails for one instance.

        Runs in a worker thread and must not modify instance or context
            data. The staging directory and new representations are stored
            to the result instead.

        Args:
            instance (pyblish.api.Instance): Instance to process.
            result (_InstanceResult): Result to store the outputs to.
            log (logging.Logger | logging.LoggerAdapter): Logger to use.

        """
        if not self.profiles:
            log.debug("No profiles present for extract review thumbnail.")
            return
        thumbnail_def = self._get_config_from_profile(instance, log)
        if not thumbnail_def:
            return

        product_name = instance.data["productName"]
        instance_repres = instance.data.get("representations")
        if not instance_repres:
            log.debug((
                "Instance {} does not have representations. Skipping"
            ).format(product_name))
            return

        log.debug(
            "Processing instance with product name {}".format(product_name)
        )

        # Skip if instance have 'review' key in data set to 'False'
        if not self._is_review_instance(instance):
            log.debug("Skipping - no review set on instance.")
            return

        # Check if already has thumbnail created
        if self._already_has_thumbnail(instance_repres, log):
            log.debug("Thumbnail representation already present.")
            return

        # skip crypto passes.
        # TODO: This is just a quick fix and has its own side-effects - it is
        #       affecting every prouct name with `crypto` in its name.
        #       This must be solved properly, maybe using tags on
        #       representation that can be determined much earlier and
        #       with better precision.
        if "crypto" in product_name.lower():
            log.debug("Skipping crypto passes.")
            return

        # first check for any explicitly marked representations for thumbnail
        explicit_repres = self._get_explicit_repres_for_thumbnail(
            instance, log
        )
        if explicit_repres:
            filtered_repres = explicit_repres
        else:
            filtered_repres = self._get_filtered_repres(instance, log)

        if not filtered_repres:
            log.info(
                "Instance doesn't have representations that can be used "
                "as source for thumbnail. Skipping thumbnail extraction."
            )
            return

        # Create temp directory for thumbnail
        # - this is to avoid "override" of source file
        dst_staging = tempfile.mkdtemp(prefix="pyblish_tmp_")
        log.debug(
            "Create temp directory {} for thumbnail".format(dst_staging)
        )
        # Store new staging to cleanup paths
        result.staging_dir = dst_staging

        oiio_supported = is_oiio_supported()
        thumbnail_created = False
        project_settings = instance.context.data["project_settings"]
        review_layers = get_default_reviewable_layers(project_settings)
        for repre in filtered_repres:
            # Reset for each iteration to handle cases where multiple
            # reviewable thumbnails are needed
            repre_thumb_created = False
            repre_files = repre["files"]
            src_staging = os.path.normpath(repre["stagingDir"])
            if not isinstance(repre_files, (list, tuple)):
                # convert any video file to frame so oiio doesn't need to
                # read video file (it is slow) and also we are having control
                # over which frame is used for thumbnail
                # this will also work with ffmpeg fallback conversion in case
                # oiio is not supported
                repre_extension = os.path.splitext(repre_files)[1]
                if repre_extension in VIDEO_EXTENSIONS:
                    video_file_path = os.path.join(
                        src_staging, repre_files
                    )
                    file_path = self._create_frame_from_video(
                        video_file_path,
                        dst_staging,
                        thumbnail_def,
                        log,
                    )
                    if file_path:
                        src_staging, input_file = os.path.split(file_path)
                else:
                    # if it is not video file then just use first file
                    input_file = repre_files
            else:
                repre_files_thumb = copy.deepcopy(repre_files)
                # exclude first frame if slate in representation tags
                if "slate-frame" in repre.get("tags", []):
                    repre_files_thumb = repre_files_thumb[1:]
                file_index = int(
                    float(len(repre_files_thumb)) * thumbnail_def.duration_split  # noqa: E501
                )
                input_file = repre_files[file_index]

            full_input_path = os.path.join(src_staging, input_file)
            log.debug("input {}".format(full_input_path))

            filename = os.path.splitext(input_file)[0]
            jpeg_file = filename + "_thumb.jpg"
            full_output_path = os.path.join(dst_staging, jpeg_file)
            colorspace_data = repre.get("colorspaceData")

            # NOTE We should find out what is happening here. Why don't we
            #   use oiiotool all the time if it is available? Only possible
            #   reason might be that video files should be converted using
            #   ffmpeg, but other then that, we should use oiio all the time.
            #   - We should also probably get rid of the ffmpeg settings...

            # only use OIIO if it is supported and representation has
            # colorspace data
            if oiio_supported and colorspace_data:
                log.debug(
                    "Trying to convert with OIIO "
                    "with colorspace data: {}".format(colorspace_data)
                )
                # If the input can read by OIIO then use OIIO method for
                # conversion otherwise use ffmpeg
                anatomy = instance.context.data["anatomy"]
                repre_thumb_created = self._create_colorspace_thumbnail(
                    full_input_path,
                    full_output_path,
                    repre,
                    thumbnail_def,
                    anatomy=anatomy,
                    review_layers=review_layers,
                    log=log,
                )

            # Try to use FFMPEG if OIIO is not supported or for cases when
            #   oiiotool isn't available or representation is not having
            #   colorspace data
            if not repre_thumb_created:
                repre_thumb_created = self._create_thumbnail_ffmpeg(
                    full_input_path,
                    full_output_path,
                    thumbnail_def,
                    review_layers,
                    log,
                )

            # Skip representation and try next one if wasn't created
            if not repre_thumb_created and oiio_supported:
                repre_thumb_created = self._create_thumbnail_oiio(
                    full_input_path,
                    full_output_path,
                    thumbnail_def,
                    review_layers,
                    log,
                )

            if not repre_thumb_created:
                continue

            thumbnail_created = True
            if len(explicit_repres) > 1:
                repre_name = "thumbnail_{}".format(repre["outputName"])
            else:
                repre_name = "thumbnail"

            new_repre_tags = ["thumbnail"]
            # for workflows which needs to have thumbnails published as
            # separate representations `delete` tag should not be added
            if not thumbnail_def.integrate_thumbnail:
                new_repre_tags.append("delete")

            new_repre = {
                "name": repre_name,
                "ext": "jpg",
                "files": jpeg_file,
                "stagingDir": dst_staging,
                "thumbnail": True,
                "tags": new_repre_tags,
                # If source image is jpg then there can be clash when
                # integrating to making the output name explicit.
                "outputName": "thumbnail"
            }

            # adding representation
            result.representations.append(new_repre)

            if explicit_repres:
                # this key will then align assetVersion ftrack thumbnail sync
                new_repre["outputName"] = (
                    repre.get("outputName") or repre["name"])
                log.debug(
                    "Adding explicit thumbnail representation: {}".format(
                        new_repre))
            else:
                log.debug(
                    "Adding thumbnail representation: {}".format(new_repre)
                )
                # There is no need to create more then one thumbnail
                break

        if not thumbnail_created:
            log.warning("Thumbnail has not been created.")

    def _is_review_instance(self, instance):
        # TODO: We should probably handle "not creating" of thumbnail
        #   other way then checking for "review" key on instance data?
        if instance.data.get("review", True):
            return True
        return False

    def _already_has_thumbnail(
        self, repres, log: logging.Logger | logging.LoggerAdapter
    ):
        for repre in repres:
            log.debug("repre {}".format(repre))
            if repre["name"] == "thumbnail":
                return True
        return False

    def _get_explicit_repres_for_thumbnail(
        self, instance, log: logging.Logger | logging.LoggerAdapter
    ):
        src_repres = instance.data.get("representations") or []
        # This is mainly for Nuke where we have multiple representations for
        #   one instance and representations are tagged for thumbnail.
        # First check if any of the representations have
        # `need_thumbnail` in tags and add them to filtered_repres
        need_thumb_repres = [
            repre for repre in src_repres
            if "need_thumbnail" in repre.get("tags", [])
            if "publish_on_farm" not in repre.get("tags", [])
        ]
        if not need_thumb_repres:
            return []

        log.info(
            "Instance has representation with tag `need_thumbnail`. "
            "Using only this representations for thumbnail creation. "
        )
        log.debug(
            "Representations: {}".format(need_thumb_repres)
        )
        return need_thumb_repres

    def _get_filtered_repres(
        self, instance, log: logging.Logger | logging.LoggerAdapter
    ):
        review_repres = []
        other_repres = []
        src_repres = instance.data.get("representations") or []

        for repre in src_repres:
            log.debug(repre)
            tags = repre.get("tags") or []

            if "publish_on_farm" in tags:
                # only process representations with are going
                # to be published locally
                continue

            if not repre.get("files"):
                log.debug((
                    "Representation \"{}\" doesn't have files. Skipping"
                ).format(repre["name"]))
                continue

            if "review" in tags:
                review_repres.append(repre)
            elif self._is_valid_images_repre(repre):
                other_repres.append(repre)

        return review_repres + other_repres

    def _is_valid_images_repre(self, repre: dict) -> bool:
        """Check if representation contains valid image files

        Args:
            repre (dict): representation

        Returns:
            bool: whether the representation has the valid image content
        """
        # Get first file's extension
        first_file = repre["files"]
        if isinstance(first_file, (list, tuple)):
            first_file = first_file[0]

        ext = os.path.splitext(first_file)[1].lower()

        return ext in IMAGE_EXTENSIONS or ext in VIDEO_EXTENSIONS

    def _create_colorspace_thumbnail(
        self,
        src_path: str,
        dst_path: str,
        repre: dict,
        thumbnail_def: ThumbnailDef,
        anatomy: "Anatomy",
        review_layers: list[str],
        log: logging.Logger | logging.LoggerAdapter,
    ) -> bool:
        """Create thumbnail using OIIO tool oiiotool

        Args:
            src_path (str): path to source file
            dst_path (str): path to destination file
            repre (dict): colorspace data from representation
                keys:
                    colorspace (str)
                    config (dict)
                    display (str | None)
                    view (str | None)
            thumbnail_def (ThumbnailDefinition): Thumbnail definition.
            anatomy (Anatomy): Current project Anatomy.
            review_layers (list[str]): List of reviewable layers.
            log (logging.Logger | logging.LoggerAdapter): Logger to use.

        Returns:
            bool: Whether a thumbnail has been created.
        """

        ocio_config_path = get_representation_ocio_config_path(
            repre,
            anatomy=anatomy,
            logger=log
        )
        if not ocio_config_path:
            log.debug("Unable to find representation OCIO file.")
            return False

        colorspace_data: dict = repre["colorspaceData"]

        log.info(f"Extracting thumbnail {dst_path}")
        resolution_arg = self._get_resolution_args(
            "oiiotool", src_path, thumbnail_def, review_layers, log
        )

        repre_display = colorspace_data.get("display")
        repre_view = colorspace_data.get("view")
        oiio_default_display = None
        oiio_default_view = None
        oiio_default_colorspace = None
        # first look into representation colorspaceData, perhaps it has
        #   display and view
        if all([repre_display, repre_view]):
            log.info(
                "Using Display & View from "
                "representation: '{} ({})'".format(
                    repre_view,
                    repre_display
                )
            )
        # if representation doesn't have display and view then use
        #   oiiotool_defaults
        elif thumbnail_def.oiiotool_defaults:
            oiiotool_defaults = thumbnail_def.oiiotool_defaults
            oiio_default_type = oiiotool_defaults["type"]
            if "colorspace" == oiio_default_type:
                oiio_default_colorspace = oiiotool_defaults["colorspace"]
            else:
                display_and_view = oiiotool_defaults["display_and_view"]
                oiio_default_display = display_and_view["display"]
                oiio_default_view = display_and_view["view"]

        try:
            oiio_color_convert(
                src_path,
                dst_path,
                ocio_config_path,
                colorspace_data["colorspace"],
                source_display=colorspace_data.get("display"),
                source_view=colorspace_data.get("view"),
                target_display=repre_display or oiio_default_display,
                target_view=repre_view or oiio_default_view,
                target_colorspace=oiio_default_colorspace,
                additional_command_args=resolution_arg,
                review_layers=review_layers,
                logger=log,
            )
        except Exception:
            log.warning(
                "Failed to create thumbnail using oiiotool",
                exc_info=True
            )
            return False

        return True

    def _create_thumbnail_oiio(
        self,
        src_path: str,
        dst_path: str,
        thumbnail_def: ThumbnailDef,
        review_layers: list[str],
        log: logging.Logger | logging.LoggerAdapter,
    ) -> bool:
        """Create thumbnail using OIIO tool

        Args:
            src_path (str): source file path
            dst_path (str): destination file path
            thumbnail_def (ThumbnailDef): Thumbnail definition.
            review_layers (list[str]): List of reviewable layers.
            log (logging.Logger | logging.LoggerAdapter): Logger to use.

        Returns:
            bool: Whether the thumbnail was successfully created.

        """
        log.debug(f"Extracting thumbnail with OIIO: {dst_path}")

        try:
            resolution_arg = self._get_resolution_args(
                "oiiotool", src_path, thumbnail_def, review_layers, log
            )
        except RuntimeError:
            log.warning(
                "Failed to create thumbnail using oiio", exc_info=True
            )
            return False

        input_info = get_oiio_info_for_input(
            src_path,
            logger=log,
            verbose=False,
        )
        try:
            input_arg, channels_arg = get_oiio_input_and_channel_args(
                input_info, review_layers=review_layers
            )
        except MissingRGBAChannelsError:
            log.debug(
                "Unable to find relevant reviewable channel for thumbnail "
                "creation"
            )
            return False
        oiio_cmd = get_oiio_tool_args(
            "oiiotool",
            input_arg, src_path,
            # Tell oiiotool which channels should be put to top stack
            #   (and output)
            "--ch", channels_arg,
            # Use first subimage
            "--subimage", "0"
        )
        oiio_cmd.extend(resolution_arg)
        oiio_cmd.extend(("-o", dst_path))
        log.debug("Running: {}".format(" ".join(oiio_cmd)))
        try:
            run_subprocess(oiio_cmd, logger=log)
            return True
        except Exception:
            log.warning(
                "Failed to create thumbnail using oiiotool",
                exc_info=True
            )
            return False

    def _create_thumbnail_ffmpeg(
        self,
        src_path: str,
        dst_path: str,
        thumbnail_def: ThumbnailDef,
        review_layers: list[str],
        log: logging.Logger | logging.LoggerAdapter,
) -> bool:
        """Create thumbnail using FFmpeg tool

        Args:
            src_path (str): source file path
            dst_path (str): destination file path
            thumbnail_def (ThumbnailDef): Thumbnail definition.
            review_layers (list[str]): List of reviewable layers.
            log (logging.Logger | logging.LoggerAdapter): Logger to use.

        Returns:
            bool: Whether the thumbnail was successfully created.

        """
        try:
            resolution_arg = self._get_resolution_args(
                "ffmpeg", src_path, thumbnail_def, review_layers, log
            )
        except RuntimeError:
            log.warning(
                "Failed to create thumbnail using ffmpeg", exc_info=True
            )
            return False

        ffmpeg_path_args = get_ffmpeg_tool_args("ffmpeg")
        ffmpeg_args = thumbnail_def.ffmpeg_args or {}

        jpeg_items = [
            subprocess.list2cmdline(ffmpeg_path_args)
        ]
        # flag for large file sizes
        max_int = 2147483647
        jpeg_items.extend([
            "-y",
            "-analyzeduration", str(max_int),
            "-probesize", str(max_int),
        ])
        # use same input args like with mov
        jpeg_items.extend(ffmpeg_args.get("input") or [])
        # input file
        jpeg_items.extend(["-i", path_to_subprocess_arg(src_path)])
        # output arguments from presets
        jpeg_items.extend(ffmpeg_args.get("output") or [])
        # we just want one frame from movie files
        jpeg_items.extend(["-frames:v", "1"])

        if resolution_arg:
            jpeg_items.extend(resolution_arg)

        # output file
        jpeg_items.append(path_to_subprocess_arg(dst_path))
        subprocess_command = " ".join(jpeg_items)

        try:
            run_subprocess(
                subprocess_command, shell=True, logger=log
            )
            return True
        except Exception:
            log.warning(
                "Failed to create thumbnail using ffmpeg",
                exc_info=True
            )
            return False

    def _create_frame_from_video(
        self,
        video_file_path: str,
        output_dir: str,
        thumbnail_def: ThumbnailDef,
        log: logging.Logger | logging.LoggerAdapter,
    ) -> str | None:
        """Convert video file to one frame image via ffmpeg"""
        # create output file path
        base_name = os.path.basename(video_file_path)
        filename = os.path.splitext(base_name)[0]
        output_thumb_file_path = os.path.join(
            output_dir, "{}.exr".format(filename))

        # Set video input attributes
        max_int = str(2147483647)
        video_data = get_ffprobe_data(video_file_path, logger=log)

        # Get duration or use a safe default (single frame)
        duration = 0
        for stream in video_data["streams"]:
            if stream.get("codec_type") == "video":
                stream_duration = float(stream.get("duration", 0))
                if stream_duration > duration:
                    duration = stream_duration

        # For very short videos, just use the first frame
        # Calculate seek position safely
        seek_position = 0.0
        # Only use timestamp calculation for videos longer than 0.1 seconds
        if duration > 0.1:
            seek_position = duration * thumbnail_def.duration_split

        # Build command args
        cmd_args = []
        if seek_position > 0.0:
            cmd_args.extend(["-ss", str(seek_position)])

        # Add generic ffmpeg commands
        cmd_args.extend([
            "-i", video_file_path,
            "-analyzeduration", max_int,
            "-probesize", max_int,
            "-y",
            "-frames:v", "1",
            output_thumb_file_path
        ])

        # create ffmpeg command
        cmd = get_ffmpeg_tool_args(
            "ffmpeg",
            *cmd_args
        )
        try:
            # run subprocess
            log.debug("Executing: {}".format(" ".join(cmd)))
            run_subprocess(cmd, logger=log)

            # Verify the output file was created
            if (
                os.path.exists(output_thumb_file_path)
                and os.path.getsize(output_thumb_file_path) > 0
            ):
                log.debug(
                    "Thumbnail created: {}".format(output_thumb_file_path))
                return output_thumb_file_path
            log.warning("Output file was not created or is empty")

            # Try to create thumbnail without offset
            # - skip if offset did not happen
            if "-ss" not in cmd_args:
                return None

            log.debug("Trying fallback without offset")
            # Remove -ss and its value
            ss_index = cmd_args.index("-ss")
            cmd_args.pop(ss_index)  # Remove -ss
            cmd_args.pop(ss_index)  # Remove the timestamp value

            # Create new command and try again
            cmd = get_ffmpeg_tool_args("ffmpeg", *cmd_args)
            log.debug("Fallback command: {}".format(" ".join(cmd)))
            run_subprocess(cmd, logger=log)

            if (
                os.path.exists(output_thumb_file_path)
                and os.path.getsize(output_thumb_file_path) > 0
            ):
                log.debug("Fallback thumbnail created")
                return output_thumb_file_path
            return None
        except RuntimeError as error:
            log.warning(
                "Failed intermediate thumb source using ffmpeg: {}".format(
                    error)
            )
            return None
        finally:
            # Remove output file if is empty
            if (
                os.path.exists(output_thumb_file_path)
                and os.path.getsize(output_thumb_file_path) == 0
            ):
                os.remove(output_thumb_file_path)

    def _get_resolution_args(
        self,
        application: str,
        input_path: str,
        thumbnail_def: ThumbnailDef,
        review_layers: list[str],
        log: logging.Logger | logging.LoggerAdapter,
    ) -> list:
        """Create command arguments for rescaling.

        Args:
            application (str): Application name.
            input_path (str): Input file path.
            thumbnail_def (ThumbnailDef): Thumbnail definition.
            review_layers (list[str]): List of reviewable layers.
            log (logging.Logger | logging.LoggerAdapter): Logger to use.

        Returns:
            list: List of command arguments for rescaling.
        """
        # get settings
        if thumbnail_def.target_size["type"] == "source":
            return []

        resize = thumbnail_def.target_size["resize"]
        target_width = resize["width"]
        target_height = resize["height"]

        # form arg string per application
        return get_rescaled_command_arguments(
            application,
            input_path,
            target_width,
            target_height,
            bg_color=thumbnail_def.background_color,
            review_layers=review_layers,
            log=log,
        )

    def _get_config_from_profile(
        self,
        instance: pyblish.api.Instance,
        log: logging.Logger | logging.LoggerAdapter,
    ) -> ThumbnailDef | None:
        """Returns profile if and how repre should be color transcoded."""
        host_name = instance.context.data["hostName"]
        product_base_type = instance.data.get("productBaseType")
        if not product_base_type:
            product_base_type = instance.data["productType"]
        product_name = instance.data["productName"]
        task_data = instance.data["anatomyData"].get("task", {})
        task_name = task_data.get("name")
        task_type = task_data.get("type")
        filtering_criteria = {
            "host_names": host_name,
            "product_base_types": product_base_type,
            "product_names": product_name,
            "task_names": task_name,
            "task_types": task_type,
        }
        profile = filter_profiles(
            self.profiles,
            filtering_criteria,
            logger=log
        )

        if not profile:
            log.debug(
                "Skipped instance. None of profiles in presets are for"
                f' Host name: "{host_name}"'
                f' | Product base type: "{product_base_type}"'
                f' | Product name: "{product_name}"'
                f' | Task name "{task_name}"'
                f' | Task type "{task_type}"'
            )
            return None

        return ThumbnailDef.from_dict(profile)
