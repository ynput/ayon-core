from __future__ import annotations

import html
import os
import datetime
from pathlib import Path
from typing import Optional, Any

import arrow
import ayon_api
from qtpy import QtCore, QtGui
from ayon_core.lib import Logger, NestedCacheItem
from ayon_core.lib.local_settings import get_launcher_local_dir
from ayon_core.host.interfaces import ListPublishedWorkfilesOptionalData
from ayon_core.settings import get_project_settings

from ayon_core.pipeline.anatomy import Anatomy
from ayon_core.pipeline.thumbnails import get_thumbnail_path
from ayon_core.tools.common_models.users import get_users
from ayon_core.tools.launcher.abstract import (
    WorkfileItem,
    AbstractLauncherBackend,
)
from ayon_core.tools.launcher.launcher_open_publish import (
    host_name_for_path_from_ext_map,
)
from ayon_core.tools.launcher.tray_workfile_host import TrayWorkfileHost
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

        self._applications_index: Optional[
            tuple[dict[str, Any], dict[str, str], list[str]]
        ] = None
        self._workfile_items = NestedCacheItem(
            levels=3,
            default_factory=list,
            lifetime=60,
        )
        self._tooltip_cache = {}
        self._published_tooltip_cache: dict[tuple[str, str, str], str] = {}

    def reset(self) -> None:
        self._workfile_items.reset()
        self._tooltip_cache.clear()
        self._published_tooltip_cache.clear()
        self._applications_index = None

    def _show_published_workfiles(self) -> bool:
        return bool(self._controller.get_show_published_workfiles())

    def get_workfile_items(
        self,
        project_name: Optional[str],
        task_id: Optional[str],
    ) -> list[WorkfileItem]:
        if not project_name or not task_id:
            return []

        folder_id = self._controller.get_selected_folder_id()
        pub_flag = "1" if self._show_published_workfiles() else "0"
        cache = self._workfile_items[project_name][task_id][pub_flag]
        if cache.is_valid:
            return cache.get_data()

        if self._show_published_workfiles():
            items = self._get_published_workfile_items(
                project_name, folder_id, task_id
            )
        else:
            items = self._get_db_workfile_items(project_name, task_id)

        cache.update_data(items)
        return items

    def _get_db_workfile_items(
        self,
        project_name: str,
        task_id: str,
    ) -> list[WorkfileItem]:
        project_entity = self._controller.get_project_entity(project_name)
        anatomy = Anatomy(project_name, project_entity=project_entity)
        items = []
        for workfile_entity in ayon_api.get_workfiles_info(
            project_name,
            task_ids={task_id},
            fields={"id", "path", "data", "updatedAt"},
        ):
            rootless_path = workfile_entity["path"]
            exists = False
            path = None
            try:
                path = anatomy.fill_root(rootless_path)
                exists = os.path.exists(path)
            except Exception:
                self._log.warning(
                    "Failed to fill root for workfile path",
                    exc_info=True,
                )

            mod_time = None
            if path and exists:
                mod_time = os.path.getmtime(path)

            else:
                updated_at = workfile_entity["updatedAt"]
                if updated_at:
                    mod_time = float(
                        arrow.get(updated_at).to("local").timestamp
                    )

            workfile_data = workfile_entity["data"]
            host_name = workfile_data.get("host_name")
            version = workfile_data.get("version")

            items.append(WorkfileItem(
                workfile_id=workfile_entity["id"],
                filename=os.path.basename(rootless_path),
                exists=exists,
                host_name=host_name,
                icon=self._get_host_icon(host_name),
                version=version,
                updated_at_time=mod_time,
            ))
        return items

    def _get_published_workfile_items(
        self,
        project_name: str,
        folder_id: Optional[str],
        task_id: str,
    ) -> list[WorkfileItem]:
        if not folder_id:
            return []

        product_entities = list(
            ayon_api.get_products(
                project_name,
                folder_ids={folder_id},
                product_types={"workfile"},
                fields={"id", "name"},
            )
        )

        version_entities = []
        product_ids = {product["id"] for product in product_entities}
        if product_ids:
            version_entities = list(
                ayon_api.get_versions(
                    project_name,
                    product_ids=product_ids,
                    fields={"id", "author", "taskId", "attrib.comment"},
                )
            )

        repre_entities = []
        if version_entities:
            repre_entities = list(
                ayon_api.get_representations(
                    project_name,
                    version_ids={v["id"] for v in version_entities},
                )
            )

        project_entity = self._controller.get_project_entity(project_name)
        anatomy = Anatomy(project_name, project_entity=project_entity)
        prepared_data = ListPublishedWorkfilesOptionalData(
            project_entity=project_entity,
            anatomy=anatomy,
            project_settings=get_project_settings(project_name),
            product_entities=product_entities,
            version_entities=version_entities,
            repre_entities=repre_entities,
        )

        host = TrayWorkfileHost(self._controller)
        published = host.list_published_workfiles(
            project_name,
            folder_id,
            prepared_data=prepared_data,
        )
        published = [p for p in published if p.task_id == task_id]

        ext_host = self.get_extension_to_host_map()

        items: list[WorkfileItem] = []
        for p in published:
            mod_time = p.file_modified or p.file_created or p.created_at
            fname = os.path.basename(p.filepath)
            host_name = host_name_for_path_from_ext_map(p.filepath, ext_host)
            items.append(
                WorkfileItem(
                    workfile_id="",
                    filename=fname,
                    exists=p.available,
                    host_name=host_name,
                    icon=self._get_host_icon(host_name),
                    version=None,
                    updated_at_time=mod_time,
                    representation_id=p.representation_id,
                    representation_path=p.filepath,
                )
            )
        return items

    def _ensure_applications_index(
        self,
    ) -> tuple[dict[str, Any], dict[str, str], list[str]]:
        """Single pass over app groups: icons, ext→host (first wins), all exts."""
        if self._applications_index is not None:
            return self._applications_index

        host_icons: dict[str, Any] = {}
        ext_to_host: dict[str, str] = {}
        ext_union: set[str] = set()

        try:
            addons_manager = self._controller.get_addons_manager()
            applications_addon = addons_manager["applications"]
            mgr = applications_addon.get_applications_manager()
            groups = sorted(
                mgr.app_groups.values(),
                key=lambda g: (g.host_name or ""),
            )
            for app_group in groups:
                hn = app_group.host_name
                if not hn:
                    continue
                icon_filename = app_group.icon
                if icon_filename and hn not in host_icons:
                    host_icons[hn] = applications_addon.get_app_icon_url(
                        icon_filename, server=True
                    )
                host_addon = addons_manager.get_host_addon(hn)
                if host_addon is None:
                    continue
                getter = getattr(host_addon, "get_workfile_extensions", None)
                if not callable(getter):
                    continue
                for raw in getter() or []:
                    ext = str(raw).lower().lstrip(".")
                    if ext:
                        ext_union.add(ext)
                        if ext not in ext_to_host:
                            ext_to_host[ext] = hn
        except Exception:
            self._log.warning(
                "Failed to build applications host index",
                exc_info=True,
            )

        sorted_exts = sorted(ext_union)
        self._applications_index = (host_icons, ext_to_host, sorted_exts)
        return self._applications_index

    def get_extension_to_host_map(self) -> dict[str, str]:
        _, ext_map, _ = self._ensure_applications_index()
        return ext_map

    def get_all_workfile_extensions(self) -> list[str]:
        _, _, exts = self._ensure_applications_index()
        return exts

    def _get_host_icon(
        self, host_name: Optional[str]
    ) -> str | None:
        host_icons, _, _ = self._ensure_applications_index()
        return host_icons.get(host_name)

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

    def get_published_representation_tooltip_data(
        self,
        project_name: Optional[str],
        task_id: Optional[str],
        representation_id: Optional[str],
        representation_filepath: Optional[str],
    ) -> str:
        """Rich-text tooltip for a published representation row."""
        if not project_name or not task_id or not representation_id:
            return ""
        cache_key = (project_name, task_id, representation_id)
        if cache_key in self._published_tooltip_cache:
            return self._published_tooltip_cache[cache_key]
        try:
            out = self._build_published_representation_tooltip(
                project_name,
                representation_id,
                representation_filepath or "",
            )
        except Exception:
            self._log.warning(
                "Failed to build published representation tooltip",
                exc_info=True,
            )
            out = ""
        if not out and representation_filepath:
            out = _workfile_tooltip_metadata_table(
                [("Path", representation_filepath)]
            )
        self._published_tooltip_cache[cache_key] = out
        return out

    def _build_published_representation_tooltip(
        self,
        project_name: str,
        representation_id: str,
        representation_filepath: str,
    ) -> str:
        """Build published tooltip like workfile tooltip (thumb + table rows)."""
        rep_entity = ayon_api.get_representation_by_id(
            project_name,
            representation_id,
        )
        if not rep_entity:
            return ""

        version_entity = None
        version_id = rep_entity.get("versionId")
        if version_id:
            version_entity = ayon_api.get_version_by_id(
                project_name,
                version_id,
                fields={
                    "author",
                    "attrib",
                    "createdAt",
                    "updatedAt",
                    "updatedBy",
                    "createdBy",
                    "thumbnailId",
                },
            )

        datetime_format = "%b %d %Y %H:%M:%S"
        file_size = file_created = file_modified = None
        if representation_filepath and os.path.exists(representation_filepath):
            st = os.stat(representation_filepath)
            file_size = st.st_size
            file_created = st.st_ctime
            file_modified = st.st_mtime

        thumbnail_id = None
        description = ""
        created_by = None
        updated_by = None
        created_at_v = None
        updated_at_v = None

        if version_entity:
            thumbnail_id = version_entity.get("thumbnailId")
            created_by = (
                version_entity.get("createdBy") or version_entity.get("author")
            )
            updated_by = version_entity.get("updatedBy")
            attrib_v = version_entity.get("attrib") or {}
            description = (attrib_v.get("comment") or "").strip()
            created_at_v = version_entity.get("createdAt")
            updated_at_v = version_entity.get("updatedAt")

        usernames = [u for u in (created_by, updated_by) if u]
        user_by_name: dict[str, str] = {}
        if usernames and project_name:
            for user in get_users(project_name, usernames=usernames):
                name = user.get("name")
                if name:
                    full = (user.get("attrib") or {}).get("fullName") or name
                    user_by_name[name] = full

        def section(label: str, parts: list[str]) -> list[tuple[str, str]]:
            if not parts:
                return []
            return [(label, "\n".join(parts))]

        rows: list[tuple[str, str]] = []
        size_str = _file_size_to_string(file_size)
        if size_str:
            rows.append(("Size", size_str))

        created_parts: list[str] = []
        if created_by:
            created_parts.append(user_by_name.get(created_by, created_by))
        if file_created:
            created_parts.append(
                datetime.datetime.fromtimestamp(file_created).strftime(
                    datetime_format
                )
            )
        elif created_at_v:
            created_parts.append(
                datetime.datetime.fromtimestamp(
                    float(arrow.get(created_at_v).to("local").timestamp)
                ).strftime(datetime_format)
            )
        elif rep_entity.get("createdAt"):
            created_parts.append(
                datetime.datetime.fromtimestamp(
                    float(
                        arrow.get(rep_entity["createdAt"]).to("local").timestamp
                    )
                ).strftime(datetime_format)
            )
        rows.extend(section("Created", created_parts))

        modified_parts: list[str] = []
        if updated_by:
            modified_parts.append(user_by_name.get(updated_by, updated_by))
        if file_modified:
            modified_parts.append(
                datetime.datetime.fromtimestamp(file_modified).strftime(
                    datetime_format
                )
            )
        elif updated_at_v:
            modified_parts.append(
                datetime.datetime.fromtimestamp(
                    float(arrow.get(updated_at_v).to("local").timestamp)
                ).strftime(datetime_format)
            )
        rows.extend(section("Modified", modified_parts))

        if description:
            rows.append(("Comment", description))

        if not rows:
            return ""

        table_block = _workfile_tooltip_metadata_table(rows)
        img_html = ""
        if thumbnail_id and version_id:
            try:
                thumb_path = get_thumbnail_path(
                    project_name,
                    "version",
                    version_id,
                    thumbnail_id,
                )
                if thumb_path and os.path.isfile(thumb_path):
                    display_path = _get_scaled_thumbnail_path(
                        thumb_path,
                        project_name,
                        version_id,
                        thumbnail_id,
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
