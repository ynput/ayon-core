"""Loader grid thumbnails: derivatives cache and representation resolves."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, List, Optional, Tuple

import ayon_api
from qtpy import QtCore, QtGui

from ayon_core.lib.local_settings import get_launcher_local_dir
from ayon_core.lib.transcoding import VIDEO_EXTENSIONS
from ayon_core.pipeline import Anatomy
from ayon_core.pipeline.load import get_representation_path_with_anatomy

if TYPE_CHECKING:
    from ayon_core.tools.loader.abstract import RepreItem

GRID_THUMB_MAX_PX = 256
GRID_THUMB_JPEG_QUALITY = 80
SMALL_IMAGE_BYTES = 256 * 1024


def get_grid_derivatives_dir(project_name: str) -> str:
    """JPEG cache under launcher thumbnails (ThumbnailsCache tree)."""
    root = os.path.join(
        get_launcher_local_dir("thumbnails"),
        "grid_derivatives",
        project_name,
    )
    os.makedirs(root, exist_ok=True)
    return root


def cache_key_for_source(version_id: str, src_path: str) -> str:
    try:
        mtime = int(os.path.getmtime(src_path))
    except OSError:
        mtime = 0
    safe_vid = version_id.replace(os.sep, "_").replace(":", "_")
    return f"{safe_vid}_{mtime}"


def is_image_file_path(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in {
        ".jpg",
        ".jpeg",
        ".png",
        ".tif",
        ".tiff",
        ".exr",
    }


def is_video_file_path(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in VIDEO_EXTENSIONS


def resolve_representation_file_path(
    project_name: str,
    representation_id: str,
) -> Optional[str]:
    """Return an on-disk path for a representation, or None."""
    try:
        repre_entity = ayon_api.get_representation_by_id(
            project_name, representation_id
        )
        if not repre_entity:
            return None
        anatomy = Anatomy(project_name)
        file_path = get_representation_path_with_anatomy(repre_entity, anatomy)
        if not file_path:
            return None
        if hasattr(file_path, "normalized"):
            fp = str(file_path.normalized())
        else:
            fp = str(file_path)
        if os.path.isfile(fp):
            return fp
    except Exception:
        return None
    return None


def iter_repre_probe_order(items: List["RepreItem"]) -> List["RepreItem"]:
    """Prefer thumbnail / image-like reps before obvious video reps."""
    thumbs: List["RepreItem"] = []
    img_like: List["RepreItem"] = []
    rest: List["RepreItem"] = []
    videos: List["RepreItem"] = []
    for item in items:
        n = (item.representation_name or "").lower()
        if "thumbnail" in n or n == "thumbnail":
            thumbs.append(item)
        elif "h264" in n or any(
            x in n for x in ("mp4", "mov", "avi", "mkv", "webm")
        ):
            videos.append(item)
        elif n in ("jpg", "jpeg", "png", "tif", "tiff", "exr"):
            img_like.append(item)
        else:
            rest.append(item)
    return thumbs + img_like + rest + videos


def optimize_image_to_grid_cache(
    src_path: str,
    project_name: str,
    cache_key: str,
) -> Optional[str]:
    """Downscale image to grid-sized JPEG in derivatives cache."""
    if not src_path or not os.path.isfile(src_path):
        return None
    try:
        if os.path.getsize(src_path) <= SMALL_IMAGE_BYTES:
            return src_path
    except OSError:
        return None

    out_dir = get_grid_derivatives_dir(project_name)
    out_path = os.path.join(out_dir, f"i_{cache_key}.jpg")
    if os.path.isfile(out_path):
        try:
            if os.path.getmtime(out_path) >= os.path.getmtime(src_path):
                return out_path
        except OSError:
            pass

    img = QtGui.QImage(src_path)
    if img.isNull():
        return None
    img = img.scaled(
        GRID_THUMB_MAX_PX,
        GRID_THUMB_MAX_PX,
        QtCore.Qt.AspectRatioMode.KeepAspectRatio,
        QtCore.Qt.TransformationMode.SmoothTransformation,
    )
    if not img.save(out_path, "JPEG", GRID_THUMB_JPEG_QUALITY):
        return None
    return out_path


def extract_video_first_frame_to_cache(
    video_path: str,
    project_name: str,
    cache_key: str,
) -> Optional[str]:
    """Extract first ffmpeg frame into persistent grid derivatives cache."""
    from ayon_core.lib import get_ffmpeg_tool_args, run_subprocess

    if not video_path or not os.path.isfile(video_path):
        return None

    out_dir = get_grid_derivatives_dir(project_name)
    out_path = os.path.join(out_dir, f"v_{cache_key}.jpg")
    if os.path.isfile(out_path):
        try:
            if os.path.getmtime(out_path) >= os.path.getmtime(video_path):
                return out_path
        except OSError:
            pass

    cmd = get_ffmpeg_tool_args(
        "ffmpeg",
        "-i",
        video_path,
        "-frames:v",
        "1",
        "-update",
        "1",
        "-y",
        out_path,
    )
    try:
        run_subprocess(cmd)
    except Exception:
        return None

    if os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
        return out_path
    return None


def pixmap_from_cached_video_preview(
    video_path: str,
    project_name: str,
    cache_key: str,
) -> Optional[QtGui.QPixmap]:
    """Load pixmap from cached ffmpeg preview (sidebar widget use)."""
    path = extract_video_first_frame_to_cache(
        video_path, project_name, cache_key
    )
    if not path:
        return None
    pix = QtGui.QPixmap(path)
    if pix.isNull():
        return None
    return pix


def pick_grid_thumbnail_sync_and_jobs(
    project_name: str,
    version_id: str,
    repre_items: List["RepreItem"],
    canonical_path: Optional[str],
) -> Tuple[Optional[str], List[Tuple[str, str, str]]]:
    """Pick sync grid pixmap path and optional async derivative jobs.

    Priority: representation thumbnail/image files, then canonical
    ``thumbnailId`` path. Jobs: ``image`` (downscale) or ``video`` (ffmpeg).

    Returns:
        (immediate image path or None, [(kind, src_path, cache_key), ...]).
    """

    for item in iter_repre_probe_order(repre_items):
        path = resolve_representation_file_path(
            project_name, item.representation_id
        )
        if not path:
            continue
        if is_image_file_path(path):
            try:
                sz = os.path.getsize(path)
            except OSError:
                continue
            if sz <= SMALL_IMAGE_BYTES:
                return path, []
            key = cache_key_for_source(version_id, path)
            return None, [("image", path, key)]
        if is_video_file_path(path):
            key = cache_key_for_source(version_id, path)
            return None, [("video", path, key)]

    if canonical_path and os.path.isfile(canonical_path):
        if is_image_file_path(canonical_path):
            try:
                if os.path.getsize(canonical_path) <= SMALL_IMAGE_BYTES:
                    return canonical_path, []
            except OSError:
                pass
            key = cache_key_for_source(version_id, canonical_path)
            return None, [("image", canonical_path, key)]

    return None, []
