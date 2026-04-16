"""Representation-based reviewable provider (current/legacy approach)."""

import os

from .base import ReviewableProvider


class RepresentationProvider(ReviewableProvider):
    """Provider for representation-based reviewables.

    This is the traditional approach where reviewable videos are
    stored as representations of versions. Checks disk first for
    both videos (h264_*) and images (thumbnail representations).
    """

    priority = 5  # Highest priority - check disk first
    identifier = "representation"
    label = "Representations"

    def get_reviewable_path(self, project_name, version_ids, controller):
        """Get reviewable (video or image) from representations on disk.

        Priority order:
        1. h264_* video representations (highest priority)
        2. Other video representations
        3. Thumbnail image representations (jpg, png, etc.)

        Args:
            project_name (str): Project name
            version_ids (set[str]): Version IDs to check
            controller: Loader controller instance

        Returns:
            Optional[str]: Path to video/image file if found, None otherwise
        """
        if not version_ids or not project_name:
            return None

        try:
            import ayon_api
            from ayon_core.pipeline import Anatomy
            from ayon_core.pipeline.load import (
                get_representation_path_with_anatomy,
            )

            # Process each version separately to avoid returning stale results
            # when version selection changes
            for version_id in version_ids:
                repre_items = controller.get_representation_items(
                    project_name, {version_id}
                )

                # Categorize representations by priority
                h264_video_repres = []
                other_video_repres = []
                thumbnail_repres = []

                for repre_item in repre_items:
                    repre_name = repre_item.representation_name.lower()

                    # Check if it's an h264 video
                    if "h264" in repre_name:
                        h264_video_repres.append(repre_item)
                    # Check if it's a thumbnail/image
                    elif "thumbnail" in repre_name or repre_name in [
                        "jpg",
                        "jpeg",
                        "png",
                        "tif",
                        "tiff",
                        "exr",
                    ]:
                        thumbnail_repres.append(repre_item)
                    # Other representations (might be videos)
                    else:
                        other_video_repres.append(repre_item)

                # Try in priority order: h264 videos → other videos → thumbnails
                for repre_item in (
                    h264_video_repres + other_video_repres + thumbnail_repres
                ):
                    representation_id = repre_item.representation_id
                    try:
                        repre_entity = ayon_api.get_representation_by_id(
                            project_name, representation_id
                        )
                        if repre_entity:
                            anatomy = Anatomy(project_name)
                            file_path = get_representation_path_with_anatomy(
                                repre_entity, anatomy
                            )
                            if file_path:
                                if hasattr(file_path, "normalized"):
                                    file_path_str = str(file_path.normalized())
                                else:
                                    file_path_str = str(file_path)

                                # Check if file exists on disk
                                if os.path.exists(file_path_str):
                                    # For videos, verify it's a video file
                                    if controller.is_video_file(file_path_str):
                                        controller.log.info(
                                            f"Found video representation on disk: {file_path_str}"
                                        )
                                        return file_path_str
                                    # For images, verify it's an image file
                                    elif self._is_image_file(file_path_str):
                                        controller.log.info(
                                            f"Found thumbnail representation on disk: {file_path_str}"
                                        )
                                        return file_path_str
                    except Exception as e:
                        controller.log.debug(
                            f"Failed to get representation path "
                            f"for {representation_id}: {e}"
                        )
                        continue
        except Exception as e:
            controller.log.warning(f"RepresentationProvider failed: {e}")

        return None

    def _is_image_file(self, filepath):
        """Check if file is an image file."""
        if not filepath:
            return False
        ext = os.path.splitext(filepath)[1].lower()
        return ext in [".jpg", ".jpeg", ".png", ".tif", ".tiff", ".exr"]

    def is_available(self, project_name, controller):
        """Always available as fallback.

        Args:
            project_name (str): Project name
            controller: Loader controller instance

        Returns:
            bool: Always True
        """
        return True
