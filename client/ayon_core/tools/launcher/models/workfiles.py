import html
import os
import datetime
from pathlib import Path
from typing import Optional, Any

import ayon_api
from qtpy import QtCore, QtGui
from ayon_core.lib import Logger, NestedCacheItem
from ayon_core.lib.local_settings import get_launcher_local_dir

from ayon_core.pipeline import Anatomy
from ayon_core.tools.common_models.users import get_users
from ayon_core.tools.launcher.abstract import (
    WorkfileItem,
    AbstractLauncherBackend,
)

# Max thumbnail size in tooltip; Qt rich text often ignores CSS max-width
# on img tags.
_TOOLTIP_THUMB_MAX = 160


def _file_size_to_string(size: Optional[int]) -> str:
    """Human-readable byte size for tooltips; empty if unknown."""
    if size is None:
        return ""
    try:
        n = int(size)
    except (TypeError, ValueError):
        return ""
    if n < 0:
        return ""
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    value = float(n)
    idx = 0
    while value >= 1024.0 and idx < len(units) - 1:
        value /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(value)} {units[idx]}"
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{text} {units[idx]}"


def _workfile_tooltip_metadata_table(rows: list[tuple[str, str]]) -> str:
    """Two-column HTML table for workfile tooltip (replaces ASCII pre block)."""
    if not rows:
        return ""
    parts = [
        "<table style='border-collapse:collapse;margin:0'>",
    ]
    for key, val in rows:
        esc_key = html.escape(str(key))
        esc_val = html.escape(str(val) if val is not None else "").replace(
            "\n", "<br/>"
        )
        parts.append(
            "<tr>"
            "<td style='padding:2px 8px 2px 0;white-space:nowrap;"
            "vertical-align:top;font-weight:600'>%s</td>"
            "<td style='padding:2px 0;vertical-align:top'>%s</td>"
            "</tr>" % (esc_key, esc_val)
        )
    parts.append("</table>")
    return "".join(parts)


def _get_scaled_thumbnail_path(
    thumb_path: str,
    project_name: str,
    workfile_id: str,
    thumbnail_id: str,
    max_size: int = _TOOLTIP_THUMB_MAX,
) -> Optional[str]:
    """Scale thumbnail to max_size in cache; return tooltip file URI."""
    img = QtGui.QImage(thumb_path)
    if img.isNull():
        return thumb_path
    w, h = img.width(), img.height()
    if w <= max_size and h <= max_size:
        return thumb_path
    scaled = img.scaled(
        max_size,
        max_size,
        QtCore.Qt.KeepAspectRatio,
        QtCore.Qt.SmoothTransformation,
    )
    tooltip_dir = os.path.join(
        get_launcher_local_dir("thumbnails"), project_name, "tooltip"
    )
    try:
        os.makedirs(tooltip_dir, exist_ok=True)
    except OSError:
        return thumb_path
    out_path = os.path.join(tooltip_dir, f"{workfile_id}_{thumbnail_id}.png")
    if not scaled.save(out_path):
        return thumb_path
    return out_path


class WorkfilesModel:
    def __init__(self, controller: AbstractLauncherBackend):
        self._controller = controller

        self._log = Logger.get_logger(self.__class__.__name__)

        self._host_icons = None
        self._workfile_items = NestedCacheItem(
            levels=2,
            default_factory=list,
            lifetime=60,
        )
        self._tooltip_cache = {}

    def reset(self) -> None:
        self._workfile_items.reset()
        self._tooltip_cache.clear()

    def get_workfile_items(
        self,
        project_name: Optional[str],
        task_id: Optional[str],
    ) -> list[WorkfileItem]:
        if not project_name or not task_id:
            return []

        cache = self._workfile_items[project_name][task_id]
        if cache.is_valid:
            return cache.get_data()

        project_entity = self._controller.get_project_entity(project_name)
        anatomy = Anatomy(project_name, project_entity=project_entity)
        items = []
        for workfile_entity in ayon_api.get_workfiles_info(
            project_name, task_ids={task_id}, fields={"id", "path", "data"}
        ):
            rootless_path = workfile_entity["path"]
            exists = False
            try:
                path = anatomy.fill_root(rootless_path)
                exists = os.path.exists(path)
            except Exception:
                self._log.warning(
                    "Failed to fill root for workfile path",
                    exc_info=True,
                )
            workfile_data = workfile_entity["data"]
            host_name = workfile_data.get("host_name")
            version = workfile_data.get("version")

            items.append(
                WorkfileItem(
                    workfile_id=workfile_entity["id"],
                    filename=os.path.basename(rootless_path),
                    exists=exists,
                    icon=self._get_host_icon(host_name),
                    version=version,
                    host_name=host_name,
                )
            )
        cache.update_data(items)
        return items

    def _get_host_icon(
        self, host_name: Optional[str]
    ) -> Optional[dict[str, Any]]:
        if self._host_icons is None:
            host_icons = {}
            try:
                host_icons = self._get_host_icons()
            except Exception:
                self._log.warning(
                    "Failed to get host icons",
                    exc_info=True,
                )
            self._host_icons = host_icons
        return self._host_icons.get(host_name)

    def _get_host_icons(self) -> dict[str, Any]:
        addons_manager = self._controller.get_addons_manager()
        applications_addon = addons_manager["applications"]
        apps_manager = applications_addon.get_applications_manager()
        output = {}
        for app_group in apps_manager.app_groups.values():
            host_name = app_group.host_name
            icon_filename = app_group.icon
            if not host_name or not icon_filename:
                continue
            icon_url = applications_addon.get_app_icon_url(
                icon_filename, server=True
            )
            output[host_name] = icon_url
        return output

    def get_workfile_tooltip_data(
        self,
        project_name: Optional[str],
        task_id: Optional[str],
        workfile_id: Optional[str],
    ) -> str:
        """Rich-text tooltip for a workfile (size, dates, comment)."""
        if not project_name or not task_id or not workfile_id:
            return ""
        cache_key = (project_name, task_id, workfile_id)
        if cache_key in self._tooltip_cache:
            return self._tooltip_cache[cache_key]
        try:
            out = self._build_workfile_tooltip(
                project_name, task_id, workfile_id
            )
        except Exception:
            self._log.warning(
                "Failed to build workfile tooltip",
                exc_info=True,
            )
            out = ""
        self._tooltip_cache[cache_key] = out
        return out

    def _build_workfile_tooltip(
        self,
        project_name: str,
        task_id: str,
        workfile_id: str,
    ) -> str:
        """Build workfile tooltip data."""
        project_entity = self._controller.get_project_entity(project_name)
        anatomy = Anatomy(project_name, project_entity=project_entity)
        workfiles = list(
            ayon_api.get_workfiles_info(
                project_name,
                task_ids={task_id},
                fields={
                    "id",
                    "path",
                    "createdBy",
                    "updatedBy",
                    "attrib",
                    "thumbnailId",
                },
            )
        )
        entity = next((w for w in workfiles if w["id"] == workfile_id), None)
        if not entity:
            return ""
        rootless_path = entity["path"]
        thumbnail_id = entity.get("thumbnailId")
        try:
            path = anatomy.fill_root(rootless_path)
        except Exception:
            return ""
        file_size = file_created = file_modified = None
        if path and os.path.exists(path):
            st = os.stat(path)
            file_size = st.st_size
            file_created = st.st_ctime
            file_modified = st.st_mtime
        attrib = entity.get("attrib") or {}
        description = attrib.get("description") or ""
        created_by = entity.get("createdBy")
        updated_by = entity.get("updatedBy")
        usernames = [u for u in (created_by, updated_by) if u]
        user_by_name = {}
        if usernames and project_name:
            for user in get_users(project_name, usernames=usernames):
                name = user.get("name")
                if name:
                    full = (user.get("attrib") or {}).get("fullName") or name
                    user_by_name[name] = full
        datetime_format = "%b %d %Y %H:%M:%S"

        def section(label: str, parts: list[str]) -> list[tuple[str, str]]:
            if not parts:
                return []
            return [(label, "\n".join(parts))]

        rows = []
        size_str = _file_size_to_string(file_size)
        if size_str:
            rows.append(("Size", size_str))
        created_parts = []
        if created_by:
            created_parts.append(user_by_name.get(created_by, created_by))
        if file_created:
            created_parts.append(
                datetime.datetime.fromtimestamp(file_created).strftime(
                    datetime_format
                )
            )
        rows.extend(section("Created", created_parts))
        modified_parts = []
        if updated_by:
            modified_parts.append(user_by_name.get(updated_by, updated_by))
        if file_modified:
            modified_parts.append(
                datetime.datetime.fromtimestamp(file_modified).strftime(
                    datetime_format
                )
            )
        rows.extend(section("Modified", modified_parts))
        if description:
            rows.append(("Comment", description))
        if not rows:
            return ""
        table_block = _workfile_tooltip_metadata_table(rows)
        img_html = ""
        if thumbnail_id:
            try:
                # Lazy import: pipeline.thumbnails runs ThumbnailsCache cleanup at
                # import; defer until tooltip build (tray eager-import path).
                from ayon_core.pipeline.thumbnails import get_thumbnail_path

                thumb_path = get_thumbnail_path(
                    project_name, "workfile", workfile_id, thumbnail_id
                )
                if thumb_path and os.path.isfile(thumb_path):
                    display_path = _get_scaled_thumbnail_path(
                        thumb_path, project_name, workfile_id, thumbnail_id
                    )
                    if display_path:
                        uri = Path(display_path).as_uri()
                        esc_uri = html.escape(uri)
                        div = (
                            '<div style="text-align:center;margin:0 0 4px 0">'
                        )
                        img = (
                            '<img src="%s" style="display: block; '
                            "margin: 0 auto; border: 1px solid #3d434e; "
                            'border-radius: 2px;" />'
                        )
                        img_html = (div + img + "</div>") % esc_uri
            except Exception:
                pass
        if img_html:
            return img_html + table_block
        return table_block
