"""Trait-based thumbnail extractor.

Sibling to `extract_thumbnail.py` working on trait representations.
`ExtractThumbnail` only looks at `instance.data["representations"]`, this
plugin only looks at `get_trait_representations(instance)`.

Source of the thumbnail is chosen by tags, files and slate frames of
the trait representations, color conversion uses their `ColorManaged`
trait. Thumbnail is added as a new trait representation.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import pyblish.api

from ayon_core.lib import is_oiio_supported
from ayon_core.lib.transcoding import (
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    oiio_color_convert,
)
from ayon_core.pipeline.publish import (
    add_trait_representations,
    get_trait_representations,
    has_trait_representations,
    set_trait_representations,
)
from ayon_core.pipeline.publish.lib import (
    apply_plugin_settings_automatically,
    get_default_reviewable_layers,
)
from ayon_core.pipeline.publish.trait_utils import (
    get_file_paths,
    get_ocio_config_path,
    get_tags,
    get_variant,
    has_files,
    is_sequence,
    set_files,
    set_staging_directory,
    update_persistence,
)
from ayon_core.pipeline.traits import (
    ColorManaged,
    Representation,
    Slate,
    Tagged,
    Variant,
)
from ayon_core.plugins.publish import extract_thumbnail

if TYPE_CHECKING:
    from ayon_core.pipeline import Anatomy


class ExtractThumbnailTraits(extract_thumbnail.ExtractThumbnail):
    """Create jpg thumbnail from trait-based representations."""

    label = "Extract Thumbnail (Traits)"

    @classmethod
    def apply_settings(cls, project_settings):
        # Use `ExtractThumbnail` settings, both plugins must create
        # the same thumbnail for the same instance.
        apply_plugin_settings_automatically(
            cls,
            project_settings["core"]["publish"]["ExtractThumbnail"],
        )

    def process(self, instance: pyblish.api.Instance) -> None:
        if not has_trait_representations(instance):
            return

        new_representations = self._create_thumbnails(
            instance, get_trait_representations(instance)
        )
        if new_representations:
            add_trait_representations(instance, new_representations)

        # Remove representations which were only needed for the thumbnail
        set_trait_representations(instance, [
            representation
            for representation in get_trait_representations(instance)
            if not self._is_only_thumbnail_source(representation)
        ])

    def _create_thumbnails(
        self,
        instance: pyblish.api.Instance,
        representations: list[Representation],
    ) -> list[Representation]:
        """Create thumbnail representations.

        Args:
            instance (pyblish.api.Instance): Processed instance.
            representations (list[Representation]): Representations of
                the instance.

        Returns:
            list[Representation]: Thumbnail representations.

        """
        if not self.profiles:
            self.log.debug("No profiles present for extract review thumbnail.")
            return []
        thumbnail_def = self._get_config_from_profile(instance)
        if not thumbnail_def:
            return []

        product_name = instance.data["productName"]
        if not representations:
            self.log.debug(
                f"Instance {product_name} does not have representations."
                " Skipping"
            )
            return []

        self.log.debug(f"Processing instance with product name {product_name}")
        if not self._is_review_instance(instance):
            self.log.debug("Skipping - no review set on instance.")
            return []

        if any(
            representation.name == "thumbnail"
            for representation in representations
        ):
            self.log.debug("Thumbnail representation already present.")
            return []

        # skip crypto passes.
        # TODO: This is just a quick fix and has its own side-effects - it is
        #       affecting every prouct name with `crypto` in its name.
        if "crypto" in product_name.lower():
            self.log.debug("Skipping crypto passes.")
            return []

        # first check for any explicitly marked representations for thumbnail
        explicit_repres = self._get_explicit_sources(representations)
        sources = explicit_repres or self._get_sources(representations)
        if not sources:
            self.log.info(
                "Instance doesn't have representations that can be used "
                "as source for thumbnail. Skipping thumbnail extraction."
            )
            return []

        # Create temp directory for thumbnail
        # - this is to avoid "override" of source file
        dst_staging = tempfile.mkdtemp(prefix="pyblish_tmp_")
        self.log.debug(f"Create temp directory {dst_staging} for thumbnail")
        instance.context.data["cleanupFullPaths"].append(dst_staging)

        oiio_supported = is_oiio_supported()
        project_settings = instance.context.data["project_settings"]
        review_layers = get_default_reviewable_layers(project_settings)
        anatomy = instance.context.data["anatomy"]
        thumbnails = []
        for source in sources:
            input_path = self._get_source_file(
                source, dst_staging, thumbnail_def
            )
            if input_path is None:
                continue
            self.log.debug(f"input {input_path}")

            jpeg_file = f"{Path(input_path).stem}_thumb.jpg"
            output_path = os.path.join(dst_staging, jpeg_file)

            created = False
            # only use OIIO if it is supported and representation is
            #   color managed
            if oiio_supported and source.contains_trait(ColorManaged):
                created = self._create_color_managed_thumbnail(
                    input_path,
                    output_path,
                    source.get_trait(ColorManaged),
                    thumbnail_def,
                    anatomy=anatomy,
                    review_layers=review_layers,
                )
            if not created:
                created = self._create_thumbnail_ffmpeg(
                    input_path, output_path, thumbnail_def, review_layers
                )
            if not created and oiio_supported:
                created = self._create_thumbnail_oiio(
                    input_path, output_path, thumbnail_def, review_layers
                )
            if not created:
                continue

            instance_thumb_path = instance.data.get("thumbnailPath")
            if not instance_thumb_path or not os.path.isfile(
                    instance_thumb_path):
                self.log.debug(
                    f"Adding thumbnail path to instance data: {output_path}"
                )
                instance.data["thumbnailPath"] = output_path

            thumbnail = self._create_representation(
                source,
                Path(output_path),
                thumbnail_def,
                explicit=bool(explicit_repres),
                multiple=len(explicit_repres) > 1,
            )
            thumbnails.append(thumbnail)
            self.log.debug(f"Adding thumbnail representation: {thumbnail}")
            if not explicit_repres:
                # There is no need to create more then one thumbnail
                break

        if not thumbnails:
            self.log.warning("Thumbnail has not been created.")
        return thumbnails

    def _get_explicit_sources(
            self,
            representations: list[Representation]) -> list[Representation]:
        """Get representations tagged "need_thumbnail".

        This is mainly for Nuke where we have multiple representations for
        one instance and representations are tagged for thumbnail.
        """
        sources = [
            representation
            for representation in representations
            if "need_thumbnail" in get_tags(representation)
            and "publish_on_farm" not in get_tags(representation)
        ]
        if sources:
            self.log.info(
                "Instance has representation with tag `need_thumbnail`. "
                "Using only this representations for thumbnail creation."
            )
        return sources

    def _get_sources(
            self,
            representations: list[Representation]) -> list[Representation]:
        """Get representations usable as source, review first."""
        review_sources = []
        other_sources = []
        for representation in representations:
            tags = get_tags(representation)
            # only process representations which are going to be
            #   published locally
            if "publish_on_farm" in tags:
                continue

            if not has_files(representation):
                self.log.debug(
                    f"Representation \"{representation.name}\" doesn't have"
                    " files. Skipping"
                )
                continue

            if "review" in tags:
                review_sources.append(representation)
            elif self._is_image_or_video(representation):
                other_sources.append(representation)
        return review_sources + other_sources

    @staticmethod
    def _is_image_or_video(representation: Representation) -> bool:
        ext = get_file_paths(representation)[0].suffix.lower()
        return ext in IMAGE_EXTENSIONS or ext in VIDEO_EXTENSIONS

    def _get_source_file(
        self,
        source: Representation,
        dst_staging: str,
        thumbnail_def: extract_thumbnail.ThumbnailDef,
    ) -> Optional[str]:
        """Get path to the image used for thumbnail.

        Frame from the middle (by `duration_split`) of a sequence, without
        slate frames. Frame of a video is extracted to an image.
        """
        paths = get_file_paths(source)
        if is_sequence(source):
            slate_frames = 0
            if source.contains_trait(Slate):
                slate_frames = source.get_trait(Slate).frames
            elif "slate-frame" in get_tags(source):
                slate_frames = 1
            content_paths = paths[slate_frames:] or paths
            file_index = int(
                float(len(content_paths)) * thumbnail_def.duration_split
            )
            return str(content_paths[file_index])

        path = paths[0]
        if path.suffix not in VIDEO_EXTENSIONS:
            return str(path)
        # convert any video file to frame so oiio doesn't need to
        # read video file (it is slow) and also we are having control
        # over which frame is used for thumbnail
        return self._create_frame_from_video(
            str(path), dst_staging, thumbnail_def
        )

    def _create_color_managed_thumbnail(
        self,
        src_path: str,
        dst_path: str,
        color_managed: ColorManaged,
        thumbnail_def: extract_thumbnail.ThumbnailDef,
        anatomy: Anatomy,
        review_layers: list[str],
    ) -> bool:
        """Create thumbnail using oiiotool with color conversion.

        Display and view of the representation are used as target. Target
        from `oiiotool_defaults` of thumbnail definition is used for
        representations without them.

        Returns:
            bool: Whether a thumbnail has been created.

        """
        ocio_config_path = get_ocio_config_path(
            color_managed, anatomy, logger=self.log
        )
        if not ocio_config_path:
            self.log.debug("Unable to find representation OCIO file.")
            return False

        self.log.info(f"Extracting thumbnail {dst_path}")
        resolution_arg = self._get_resolution_args(
            "oiiotool", src_path, thumbnail_def, review_layers
        )

        target_display = color_managed.display
        target_view = color_managed.view
        target_colorspace = None
        if target_display and target_view:
            self.log.info(
                "Using Display & View from representation:"
                f" '{target_view} ({target_display})'"
            )
        elif thumbnail_def.oiiotool_defaults:
            oiiotool_defaults = thumbnail_def.oiiotool_defaults
            if oiiotool_defaults["type"] == "colorspace":
                target_colorspace = oiiotool_defaults["colorspace"]
            else:
                display_and_view = oiiotool_defaults["display_and_view"]
                target_display = display_and_view["display"]
                target_view = display_and_view["view"]

        try:
            oiio_color_convert(
                src_path,
                dst_path,
                ocio_config_path,
                color_managed.color_space,
                source_display=color_managed.display,
                source_view=color_managed.view,
                target_display=target_display,
                target_view=target_view,
                target_colorspace=target_colorspace,
                additional_command_args=resolution_arg,
                review_layers=review_layers,
                logger=self.log,
            )
        except Exception:
            self.log.warning(
                "Failed to create thumbnail using oiiotool",
                exc_info=True
            )
            return False
        return True

    @staticmethod
    def _create_representation(
        source: Representation,
        path: Path,
        thumbnail_def: extract_thumbnail.ThumbnailDef,
        *,
        explicit: bool,
        multiple: bool,
    ) -> Representation:
        """Create thumbnail representation.

        Thumbnail is a new file, it does not inherit traits (e.g. color
        management) of the source representation.
        """
        source_output = get_variant(source) or source.name
        name = "thumbnail"
        if multiple:
            name = f"thumbnail_{source_output}"

        tags = ["thumbnail"]
        # for workflows which needs to have thumbnails published as
        # separate representations `delete` tag should not be added
        if not thumbnail_def.integrate_thumbnail:
            tags.append("delete")

        # Output name makes the file name explicit to avoid clash with
        #   a jpg source. It aligns thumbnail with its source for
        #   explicit thumbnails.
        variant = source_output if explicit else "thumbnail"
        representation = Representation(name=name, traits=[
            Tagged(tags=tags),
            Variant(variant=variant),
        ])
        set_files(representation, [path], sequence=False)
        set_staging_directory(representation, path.parent, is_persistent=False)
        update_persistence(representation)
        return representation

    def _is_only_thumbnail_source(
            self, representation: Representation) -> bool:
        tags = get_tags(representation)
        if "publish_on_farm" in tags:
            return False
        if "delete" in tags and "need_thumbnail" in tags:
            self.log.debug(
                f"Removing representation: {representation.name}"
            )
            return True
        return False
