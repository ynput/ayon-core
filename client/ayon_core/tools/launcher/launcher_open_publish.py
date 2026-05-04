"""Open published representation files locally (resolve path, temp copy, launch).

Also defines ``host_name_for_path_from_ext_map`` for tray listing and workfile
rows (same dotless extension convention as the applications index).

Launch is injected by the controller and should call
``ActionsModel.trigger_launch_by_host_with_workfile_path`` (applications-addon
launch), not duplicate launch logic here.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from typing import Any, Callable, Optional

__all__ = [
    "host_name_for_path_from_ext_map",
    "resolve_published_source_path",
    "run_open_published_representation_local",
]


def host_name_for_path_from_ext_map(
    path: str, ext_map: dict[str, str]
) -> Optional[str]:
    """Map filepath to host using ``ext_map`` (dotless extension keys)."""
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return ext_map.get(ext) if ext else None


def resolve_published_source_path(
    project_name: str,
    representation_filepath: str,
    get_project_entity: Callable[[str], Any],
    log: Any,
) -> Optional[str]:
    """Resolve rootless or relative published paths to a readable file path."""
    if not representation_filepath:
        return None
    if os.path.isabs(representation_filepath) and os.path.isfile(
        representation_filepath
    ):
        return representation_filepath
    try:
        from ayon_core.pipeline import Anatomy

        anatomy = Anatomy(
            project_name,
            project_entity=get_project_entity(project_name),
        )
        filled = anatomy.fill_root(representation_filepath)
        if filled and os.path.isfile(filled):
            return filled
    except Exception:
        log.debug(
            "Failed to resolve published path with anatomy",
            exc_info=True,
        )
    return None


def run_open_published_representation_local(
    project_name: Optional[str],
    folder_id: Optional[str],
    task_id: Optional[str],
    representation_filepath: str,
    *,
    get_project_entity: Callable[[str], Any],
    get_extension_to_host_map: Callable[[], dict],
    warn_user: Callable[[str], None],
    log: Any,
    launch: Callable[[str, str, str, str, str], None],
) -> None:
    """Copy published file to a temporary folder and invoke launch callback.

    Early return if `project_name`, `folder_id`, or `task_id` is missing.
    Resolves disk path via anatomy when needed, maps extension to host, copies
    to `publish_<basename>` under a `publish_` temp directory, then calls
    `launch(host_name, project_name, folder_id, task_id, dst_path)`.
    """
    if not project_name or not folder_id or not task_id:
        return

    src_path = resolve_published_source_path(
        project_name,
        representation_filepath,
        get_project_entity,
        log,
    )
    if not src_path:
        warn_user("Could not access the published file on disk.")
        return

    ext_map = get_extension_to_host_map()
    host_name = host_name_for_path_from_ext_map(src_path, ext_map)
    if not host_name:
        warn_user(
            "Could not determine which application to use for this "
            "file type."
        )
        return

    try:
        base = os.path.basename(src_path) or "publish"
        publish_temp_dir = tempfile.mkdtemp(prefix="publish_")
        dst_path = os.path.join(publish_temp_dir, f"publish_{base}")
        shutil.copy2(src_path, dst_path)
    except OSError:
        log.warning("Published file copy failed.", exc_info=True)
        warn_user("Could not copy the published file for opening.")
        return

    launch(host_name, project_name, folder_id, task_id, dst_path)
