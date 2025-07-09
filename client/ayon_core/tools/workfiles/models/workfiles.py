from __future__ import annotations
import os
import copy
import platform
import typing
from typing import Optional, Any

import ayon_api

from ayon_core.lib import (
    get_ayon_username,
    NestedCacheItem,
    CacheItem,
    Logger,
)
from ayon_core.host import (
    HostBase,
    IWorkfileHost,
    WorkfileInfo,
    PublishedWorkfileInfo,
)
from ayon_core.host.interfaces import (
    OpenWorkfileOptionalData,
    ListWorkfilesOptionalData,
    ListPublishedWorkfilesOptionalData,
    SaveWorkfileOptionalData,
    CopyWorkfileOptionalData,
    CopyPublishedWorkfileOptionalData,
)
from ayon_core.pipeline.template_data import (
    get_template_data,
    get_task_template_data,
    get_folder_template_data,
)
from ayon_core.pipeline.workfile import (
    get_workdir_with_workdir_data,
    get_workfile_template_key,
    save_workfile_info,
)
from ayon_core.pipeline.version_start import get_versioning_start
from ayon_core.tools.workfiles.abstract import (
    WorkareaFilepathResult,
    AbstractWorkfilesBackend,
)

if typing.TYPE_CHECKING:
    from ayon_core.pipeline import Anatomy

_NOT_SET = object()


class HostType(HostBase, IWorkfileHost):
    pass


class WorkfilesModel:
    """Workfiles model."""

    def __init__(
        self,
        host: HostType,
        controller: AbstractWorkfilesBackend
    ):
        self._host: HostType = host
        self._controller: AbstractWorkfilesBackend = controller

        self._log = Logger.get_logger("WorkfilesModel")
        extensions = None
        if controller.is_host_valid():
            extensions = controller.get_workfile_extensions()
        self._extensions: Optional[set[str]] = extensions

        self._current_username = _NOT_SET

        # Workarea
        self._base_data = None
        self._fill_data_by_folder_id = {}
        self._task_data_by_folder_id = {}
        self._workdir_by_context = {}
        self._workarea_file_items_mapping = {}
        self._workarea_file_items_cache = NestedCacheItem(
            levels=1, default_factory=list
        )

        # Published workfiles
        self._repre_by_id = {}
        self._published_workfile_items_cache = NestedCacheItem(
            levels=1, default_factory=list
        )

        # Entities
        self._workfile_entities_by_task_id = {}

    def reset(self):
        self._base_data = None
        self._fill_data_by_folder_id = {}
        self._task_data_by_folder_id = {}
        self._workdir_by_context = {}
        self._workarea_file_items_mapping = {}
        self._workarea_file_items_cache.reset()

        self._repre_by_id = {}
        self._published_workfile_items_cache.reset()

        self._workfile_entities_by_task_id = {}

    # Host functionality
    def get_current_workfile(self):
        return self._host.get_current_workfile()

    def open_workfile(self, folder_id, task_id, filepath):
        self._emit_event("open_workfile.started")

        failed = False
        try:
            self._open_workfile(folder_id, task_id, filepath)

        except Exception:
            failed = True
            self._log.warning("Open of workfile failed", exc_info=True)

        self._emit_event(
            "open_workfile.finished",
            {"failed": failed},
        )

    def save_current_workfile(self):
        current_file = self.get_current_workfile()
        self._host.save_workfile(current_file)

    def save_as_workfile(
        self,
        folder_id,
        task_id,
        rootless_workdir,
        workdir,
        filename,
        version,
        comment,
        description,
    ):
        self._emit_event("save_as.started")

        filepath = os.path.join(workdir, filename)
        rootless_path = f"{rootless_workdir}/{filename}"
        project_name = self._controller.get_current_project_name()
        project_entity = self._controller.get_project_entity(project_name)
        folder_entity = self._controller.get_folder_entity(
            project_name, folder_id
        )
        task_entity = self._controller.get_task_entity(
            project_name, task_id
        )

        prepared_data = SaveWorkfileOptionalData(
            project_entity=project_entity,
            anatomy=self._controller.project_anatomy,
            project_settings=self._controller.project_settings,
            rootless_path=rootless_path,
            workfile_entities=self.get_workfile_entities(task_id),
        )
        failed = False
        try:
            self._host.save_workfile_with_context(
                filepath,
                folder_entity,
                task_entity,
                version=version,
                comment=comment,
                description=description,
                prepared_data=prepared_data,
            )
            self._update_workfile_info(
                task_id, rootless_path, description
            )
            self._update_current_context(
                folder_id, folder_entity["path"], task_entity["name"]
            )

        except Exception:
            failed = True
            self._log.warning("Save as failed", exc_info=True)

        self._emit_event(
            "save_as.finished",
            {"failed": failed},
        )

    def copy_workfile_representation(
        self,
        representation_id,
        representation_filepath,
        folder_id,
        task_id,
        workdir,
        filename,
        rootless_workdir,
        version,
        comment,
        description,
    ):
        self._emit_event("copy_representation.started")

        project_name = self._project_name
        project_entity = self._controller.get_project_entity(project_name)
        folder_entity = self._controller.get_folder_entity(
            project_name, folder_id
        )
        task_entity = self._controller.get_task_entity(
            project_name, task_id
        )
        repre_entity = self._repre_by_id.get(representation_id)
        dst_filepath = os.path.join(workdir, filename)
        rootless_path = f"{rootless_workdir}/{filename}"

        prepared_data = CopyPublishedWorkfileOptionalData(
            project_entity=project_entity,
            anatomy=self._controller.project_anatomy,
            project_settings=self._controller.project_settings,
            rootless_path=rootless_path,
            representation_path=representation_filepath,
            workfile_entities=self.get_workfile_entities(task_id),
            src_anatomy=self._controller.project_anatomy,
        )
        failed = False
        try:
            self._host.copy_workfile_representation(
                project_name,
                repre_entity,
                dst_filepath,
                folder_entity,
                task_entity,
                version=version,
                comment=comment,
                description=description,
                prepared_data=prepared_data,
            )
            self._update_workfile_info(
                task_id, rootless_path, description
            )
            self._update_current_context(
                folder_id, folder_entity["path"], task_entity["name"]
            )

        except Exception:
            failed = True
            self._log.warning(
                "Copy of workfile representation failed", exc_info=True
            )

        self._emit_event(
            "copy_representation.finished",
            {"failed": failed},
        )

    def duplicate_workfile(
        self,
        folder_id,
        task_id,
        src_filepath,
        rootless_workdir,
        workdir,
        filename,
        version,
        comment,
        description
    ):
        self._emit_event("workfile_duplicate.started")

        project_name = self._controller.get_current_project_name()
        project_entity = self._controller.get_project_entity(project_name)
        folder_entity = self._controller.get_folder_entity(
            project_name, folder_id
        )
        task_entity = self._controller.get_task_entity(project_name, task_id)
        workfile_entities = self.get_workfile_entities(task_id)
        rootless_path = f"{rootless_workdir}/{filename}"
        workfile_path = os.path.join(workdir, filename)

        prepared_data = CopyWorkfileOptionalData(
            project_entity=project_entity,
            project_settings=self._controller.project_settings,
            anatomy=self._controller.project_anatomy,
            rootless_path=rootless_path,
            workfile_entities=workfile_entities,
        )
        failed = False
        try:
            self._host.copy_workfile(
                src_filepath,
                workfile_path,
                folder_entity,
                task_entity,
                version=version,
                comment=comment,
                description=description,
                prepared_data=prepared_data,
            )

        except Exception:
            failed = True
            self._log.warning("Duplication of workfile failed", exc_info=True)

        self._emit_event(
            "workfile_duplicate.finished",
            {"failed": failed},
        )

    def get_workfile_entities(self, task_id: str):
        if not task_id:
            return []
        workfile_entities = self._workfile_entities_by_task_id.get(task_id)
        if workfile_entities is None:
            workfile_entities = list(ayon_api.get_workfiles_info(
                self._project_name,
                task_ids=[task_id],
            ))
            self._workfile_entities_by_task_id[task_id] = workfile_entities
        return workfile_entities

    def get_workfile_info(
        self,
        folder_id: Optional[str],
        task_id: Optional[str],
        rootless_path: Optional[str]
    ):
        if not folder_id or not task_id or not rootless_path:
            return None

        mapping = self._workarea_file_items_mapping.get(task_id)
        if mapping is None:
            self._cache_file_items(folder_id, task_id)
            mapping = self._workarea_file_items_mapping[task_id]
        return mapping.get(rootless_path)

    def save_workfile_info(
        self,
        task_id: str,
        rootless_path: str,
        version: Optional[int],
        comment: Optional[str],
        description: Optional[str],
    ):
        self._save_workfile_info(
            task_id,
            rootless_path,
            version,
            comment,
            description,
        )

        self._update_file_description(
            task_id, rootless_path, description
        )

    def get_workarea_dir_by_context(
        self, folder_id: str, task_id: str
    ) -> Optional[str]:
        """Workarea dir for passed context.

        The directory path is based on project anatomy templates.

        Args:
            folder_id (str): Folder id.
            task_id (str): Task id.

        Returns:
            Optional[str]: Workarea dir path or None for invalid context.

        """
        if not folder_id or not task_id:
            return None
        folder_mapping = self._workdir_by_context.setdefault(folder_id, {})
        workdir = folder_mapping.get(task_id)
        if workdir is not None:
            return workdir

        workdir_data = self._prepare_fill_data(folder_id, task_id)

        workdir = get_workdir_with_workdir_data(
            workdir_data,
            self._project_name,
            anatomy=self._controller.project_anatomy,
        )
        folder_mapping[task_id] = workdir
        return workdir

    def get_workarea_file_items(self, folder_id, task_id):
        """Workfile items for passed context from workarea.

        Args:
            folder_id (Optional[str]): Folder id.
            task_id (Optional[str]): Task id.

        Returns:
            list[WorkfileInfo]: List of file items matching workarea of passed
                context.

        """
        return self._cache_file_items(folder_id, task_id)

    def get_workarea_save_as_data(
        self, folder_id: Optional[str], task_id: Optional[str]
    ) -> dict[str, Any]:
        folder_entity = None
        task_entity = None
        if folder_id:
            folder_entity = self._controller.get_folder_entity(
                self._project_name, folder_id
            )
            if folder_entity and task_id:
                task_entity = self._controller.get_task_entity(
                    self._project_name, task_id
                )

        if not folder_entity or not task_entity or self._extensions is None:
            return {
                "template_key": None,
                "template_has_version": None,
                "template_has_comment": None,
                "ext": None,
                "workdir": None,
                "rootless_workdir": None,
                "comment": None,
                "comment_hints": None,
                "last_version": None,
                "extensions": None,
            }

        anatomy = self._controller.project_anatomy
        fill_data = self._prepare_fill_data(folder_id, task_id)
        template_key = self._get_template_key(fill_data)

        current_workfile = self._controller.get_current_workfile()
        current_filename = None
        current_ext = None
        if current_workfile:
            current_filename = os.path.basename(current_workfile)
            current_ext = os.path.splitext(current_filename)[1].lower()

        extensions = self._extensions
        if not current_ext and extensions:
            current_ext = tuple(extensions)[0]

        workdir = self._get_workdir(anatomy, template_key, fill_data)

        rootless_workdir = workdir
        if platform.system().lower() == "windows":
            rootless_workdir = rootless_workdir.replace("\\", "/")

        used_roots = workdir.used_values.get("root")
        if used_roots:
            used_root_name = next(iter(used_roots))
            root_value = used_roots[used_root_name]
            workdir_end = rootless_workdir[len(root_value):].lstrip("/")
            rootless_workdir = f"{{root[{used_root_name}]}}/{workdir_end}"

        file_template = anatomy.get_template_item(
            "work", template_key, "file"
        )
        file_template_str = file_template.template

        template_has_version = "{version" in file_template_str
        template_has_comment = "{comment" in file_template_str

        file_items = self.get_workarea_file_items(folder_id, task_id)
        comment_hints = set()
        comment = None
        for item in file_items:
            filepath = item.filepath
            filename = os.path.basename(filepath)
            if filename == current_filename:
                comment = item.comment

            if item.comment:
                comment_hints.add(item.comment)
        comment_hints = list(comment_hints)

        last_version = self._get_last_workfile_version(
            file_items, task_entity
        )

        return {
            "template_key": template_key,
            "template_has_version": template_has_version,
            "template_has_comment": template_has_comment,
            "ext": current_ext,
            "workdir": workdir,
            "rootless_workdir": rootless_workdir,
            "comment": comment,
            "comment_hints": comment_hints,
            "last_version": last_version,
            "extensions": extensions,
        }

    def fill_workarea_filepath(
        self,
        folder_id: str,
        task_id: str,
        extension: str,
        use_last_version: bool,
        version: int,
        comment: str,
    ) -> WorkareaFilepathResult:
        """Fill workarea filepath based on context.

        Args:
            folder_id (str): Folder id.
            task_id (str): Task id.
            extension (str): File extension.
            use_last_version (bool): Use last version.
            version (int): Version number.
            comment (str): Comment.

        Returns:
            WorkareaFilepathResult: Workarea filepath result.

        """
        anatomy = self._controller.project_anatomy
        fill_data = self._prepare_fill_data(folder_id, task_id)

        template_key = self._get_template_key(fill_data)

        workdir = self._get_workdir(anatomy, template_key, fill_data)

        file_template = anatomy.get_template_item(
            "work", template_key, "file"
        )

        if use_last_version:
            file_items = self.get_workarea_file_items(folder_id, task_id)
            task_entity = self._controller.get_task_entity(
                self._project_name, task_id
            )
            version = self._get_last_workfile_version(
                file_items, task_entity
            )
        fill_data["version"] = version
        fill_data["ext"] = extension.lstrip(".")

        if comment:
            fill_data["comment"] = comment

        filename = file_template.format(fill_data)
        if not filename.solved:
            filename = None

        exists = False
        if filename:
            filepath = os.path.join(workdir, filename)
            exists = os.path.exists(filepath)

        return WorkareaFilepathResult(
            workdir,
            filename,
            exists
        )

    def get_published_file_items(
        self, folder_id: str, task_id: str
    ) -> list[PublishedWorkfileInfo]:
        """Published workfiles for passed context.

        Args:
            folder_id (str): Folder id.
            task_id (str): Task id.

        Returns:
            list[PublishedWorkfileInfo]: List of files for published workfiles.

        """
        if not folder_id:
            return []

        cache = self._published_workfile_items_cache[folder_id]
        if not cache.is_valid:
            project_name = self._project_name
            anatomy = self._controller.project_anatomy

            product_entities = list(ayon_api.get_products(
                project_name,
                folder_ids={folder_id},
                product_types={"workfile"},
                fields={"id", "name"}
            ))

            version_entities = []
            product_ids = {product["id"] for product in product_entities}
            if product_ids:
                # Get version docs of products with their families
                version_entities = list(ayon_api.get_versions(
                    project_name,
                    product_ids=product_ids,
                    fields={"id", "author", "taskId"},
                ))

            repre_entities = []
            if version_entities:
                repre_entities = list(ayon_api.get_representations(
                    project_name,
                    version_ids={v["id"] for v in version_entities}
                ))

            self._repre_by_id.update({
                repre_entity["id"]: repre_entity
                for repre_entity in repre_entities
            })
            project_entity = self._controller.get_project_entity(project_name)

            prepared_data = ListPublishedWorkfilesOptionalData(
                project_entity=project_entity,
                anatomy=anatomy,
                project_settings=self._controller.project_settings,
                product_entities=product_entities,
                version_entities=version_entities,
                repre_entities=repre_entities,
            )
            cache.update_data(self._host.list_published_workfiles(
                project_name,
                folder_id,
                prepared_data=prepared_data,
            ))

        items = cache.get_data()

        if task_id:
            items = [
                item
                for item in items
                if item.task_id == task_id
            ]
        return items

    @property
    def _project_name(self) -> str:
        return self._controller.get_current_project_name()

    @property
    def _host_name(self) -> str:
        return self._host.name

    def _emit_event(self, topic, data=None):
        self._controller.emit_event(topic, data, "workfiles")

    def _get_current_username(self) -> str:
        if self._current_username is _NOT_SET:
            self._current_username = get_ayon_username()
        return self._current_username

    # --- Host ---
    def _open_workfile(self, folder_id: str, task_id: str, filepath: str):
        # TODO move to workfiles pipeline
        project_name = self._project_name
        project_entity = self._controller.get_project_entity(project_name)
        folder_entity = self._controller.get_folder_entity(
            project_name, folder_id
        )
        task_entity = self._controller.get_task_entity(
            project_name, task_id
        )
        prepared_data = OpenWorkfileOptionalData(
            project_entity=project_entity,
            anatomy=self._controller.project_anatomy,
            project_settings=self._controller.project_settings,
        )
        self._host.open_workfile_with_context(
            filepath, folder_entity, task_entity, prepared_data=prepared_data
        )
        self._update_current_context(
            folder_id, folder_entity["path"], task_entity["name"]
        )

    def _update_current_context(self, folder_id, folder_path, task_name):
        self._current_folder_id = folder_id
        self._current_folder_path = folder_path
        self._current_task_name = task_name

    # --- Workarea ---
    def _reset_workarea_file_items(self, task_id: str):
        cache: CacheItem = self._workarea_file_items_cache[task_id]
        cache.set_invalid()
        self._workarea_file_items_mapping.pop(task_id, None)

    def _get_base_data(self) -> dict[str, Any]:
        if self._base_data is None:
            base_data = get_template_data(
                ayon_api.get_project(self._project_name),
                host_name=self._host_name,
            )
            self._base_data = base_data
        return copy.deepcopy(self._base_data)

    def _get_folder_data(self, folder_id: str) -> dict[str, Any]:
        fill_data = self._fill_data_by_folder_id.get(folder_id)
        if fill_data is None:
            folder = self._controller.get_folder_entity(
                self._project_name, folder_id
            )
            fill_data = get_folder_template_data(folder, self._project_name)
            self._fill_data_by_folder_id[folder_id] = fill_data
        return copy.deepcopy(fill_data)

    def _get_task_data(
        self,
        project_entity: dict[str, Any],
        folder_id: str,
        task_id: str
    ) -> dict[str, Any]:
        task_data = self._task_data_by_folder_id.setdefault(folder_id, {})
        if task_id not in task_data:
            task_entity = self._controller.get_task_entity(
                self._project_name, task_id
            )
            if task_entity:
                task_data[task_id] = get_task_template_data(
                    project_entity, task_entity
                )
        return copy.deepcopy(task_data[task_id])

    def _prepare_fill_data(
        self, folder_id: str, task_id: str
    ) -> dict[str, Any]:
        if not folder_id or not task_id:
            return {}

        base_data = self._get_base_data()
        project_name = base_data["project"]["name"]
        folder_data = self._get_folder_data(folder_id)
        project_entity = self._controller.get_project_entity(project_name)
        task_data = self._get_task_data(project_entity, folder_id, task_id)

        base_data.update(folder_data)
        base_data.update(task_data)

        return base_data

    def _cache_file_items(
        self, folder_id: Optional[str], task_id: Optional[str]
    ) -> list[WorkfileInfo]:
        if not folder_id or not task_id:
            return []

        cache: CacheItem = self._workarea_file_items_cache[task_id]
        if cache.is_valid:
            return cache.get_data()

        project_entity = self._controller.get_project_entity(
            self._project_name
        )
        folder_entity = self._controller.get_folder_entity(
            self._project_name, folder_id
        )
        task_entity = self._controller.get_task_entity(
            self._project_name, task_id
        )
        anatomy = self._controller.project_anatomy
        project_settings = self._controller.project_settings
        workfile_entities = self._controller.get_workfile_entities(task_id)

        fill_data = self._prepare_fill_data(folder_id, task_id)
        template_key = self._get_template_key(fill_data)

        prepared_data = ListWorkfilesOptionalData(
            project_entity=project_entity,
            anatomy=anatomy,
            project_settings=project_settings,
            template_key=template_key,
            workfile_entities=workfile_entities,
        )

        items = self._host.list_workfiles(
            self._project_name,
            folder_entity,
            task_entity,
            prepared_data=prepared_data,
        )
        cache.update_data(items)

        # Cache items by entity ids and rootless path
        self._workarea_file_items_mapping[task_id] = {
            item.rootless_path: item
            for item in items
        }

        return items

    def _get_template_key(self, fill_data: dict[str, Any]) -> str:
        task_type = fill_data.get("task", {}).get("type")
        # TODO cache
        return get_workfile_template_key(
            self._project_name,
            task_type,
            self._host_name,
            project_settings=self._controller.project_settings,
        )

    def _get_last_workfile_version(
        self, file_items: list[WorkfileInfo], task_entity: dict[str, Any]
    ) -> int:
        """

        Todos:
            Validate if logic of this function is correct. It does return
                last version + 1 which might be wrong.

        Args:
            file_items (list[WorkfileInfo]): Workfile items.
            task_entity (dict[str, Any]): Task entity.

        Returns:
            int: Next workfile version.

        """
        versions = {
            item.version
            for item in file_items
            if item.version is not None
        }
        if versions:
            return max(versions) + 1

        return get_versioning_start(
            self._project_name,
            self._host_name,
            task_name=task_entity["name"],
            task_type=task_entity["taskType"],
            product_type="workfile",
            project_settings=self._controller.project_settings,
        )

    def _get_workdir(
        self, anatomy: "Anatomy", template_key: str, fill_data: dict[str, Any]
    ):
        directory_template = anatomy.get_template_item(
            "work", template_key, "directory"
        )
        return directory_template.format_strict(fill_data).normalized()

    def _update_workfile_info(
        self,
        task_id: str,
        rootless_path: str,
        description: str,
    ):
        self._update_file_description(task_id, rootless_path, description)
        self._reset_workarea_file_items(task_id)

        # Update workfile entity cache if are cached
        if task_id in self._workfile_entities_by_task_id:
            workfile_entities = self.get_workfile_entities(task_id)

            target_workfile_entity = None
            for workfile_entity in workfile_entities:
                if rootless_path == workfile_entity["path"]:
                    target_workfile_entity = workfile_entity
                    break

            if target_workfile_entity is None:
                self._workfile_entities_by_task_id.pop(task_id, None)
                self.get_workfile_entities(task_id)
            else:
                target_workfile_entity["attrib"]["description"] = description

    def _update_file_description(
        self, task_id: str, rootless_path: str, description: str
    ):
        mapping = self._workarea_file_items_mapping.get(task_id)
        if not mapping:
            return
        item = mapping.get(rootless_path)
        if item is not None:
            item.description = description

    # --- Workfile entities ---
    def _save_workfile_info(
        self,
        task_id: str,
        rootless_path: str,
        version: Optional[int],
        comment: Optional[str],
        description: Optional[str],
    ):
        workfile_entity = save_workfile_info(
            self._controller.get_current_project_name(),
            task_id,
            rootless_path,
            self._controller.get_host_name(),
            version=version,
            comment=comment,
            description=description,
            workfile_entities=self.get_workfile_entities(task_id),
        )
        # Update cache
        workfile_entities = self.get_workfile_entities(task_id)
        match_idx = None
        for idx, entity in enumerate(workfile_entities):
            if entity["id"] == workfile_entity["id"]:
                # Update existing entity
                match_idx = idx
                break

        if match_idx is None:
            workfile_entities.append(workfile_entity)
        else:
            workfile_entities[match_idx] = workfile_entity
