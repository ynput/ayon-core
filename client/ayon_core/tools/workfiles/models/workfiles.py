from __future__ import annotations
import os
import copy
import uuid
import platform
import typing
from typing import Optional, Any

import ayon_api
from ayon_api.operations import OperationsSession

from ayon_core.lib import (
    get_ayon_username,
    NestedCacheItem,
    CacheItem,
)
from ayon_core.host import (
    HostBase,
    IWorkfileHost,
    WorkfileInfo,
    PublishedWorkfileInfo,
)
from ayon_core.pipeline.template_data import (
    get_template_data,
    get_task_template_data,
    get_folder_template_data,
)
from ayon_core.pipeline.workfile import (
    get_workdir_with_workdir_data,
    get_workfile_template_key,
    get_last_workfile_with_version_from_paths,
    get_comments_from_workfile_paths,
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
        self._file_items_mapping = {}
        self._file_items_cache = NestedCacheItem(
            levels=1, default_factory=list
        )

        # Entities
        self._workfile_entities_by_task_id = {}

    def reset(self):
        self._base_data = None
        self._fill_data_by_folder_id = {}
        self._task_data_by_folder_id = {}
        self._workdir_by_context = {}
        self._file_items_mapping = {}
        self._file_items_cache.reset()

        self._workfile_entities_by_task_id = {}

    def get_workfile_entities(self, task_id: str):
        if not task_id:
            return []
        workfile_entities = self._workfile_entities_by_task_id.get(task_id)
        if workfile_entities is None:
            workfile_entities = list(ayon_api.get_workfiles_info(
                self._controller.get_current_project_name(),
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

        mapping = self._file_items_mapping.get(task_id)
        if mapping is None:
            self._cache_file_items(folder_id, task_id)
            mapping = self._file_items_mapping[task_id]
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

    def reset_workarea_file_items(self, task_id):
        self._reset_file_items(task_id)

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
        filepaths = [
            item.filepath
            for item in file_items
        ]
        comment_hints, comment = get_comments_from_workfile_paths(
            filepaths,
            extensions,
            file_template,
            fill_data,
            current_filename,
        )
        last_version = self._get_last_workfile_version(
            filepaths, file_template_str, fill_data, extensions
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
            filepaths = [
                item.filepath
                for item in file_items
            ]
            version = self._get_last_workfile_version(
                filepaths,
                file_template.template,
                fill_data,
                self._extensions
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
    ) -> PublishedWorkfileInfo:
        """Published workfiles for passed context.

        Args:
            folder_id (str): Folder id.
            task_id (str): Task id.

        Returns:
            list[PublishedWorkfileInfo]: List of files for published workfiles.

        """
        project_name = self._project_name
        anatomy = self._controller.project_anatomy
        items = self._host.list_published_workfiles(
            project_name,
            folder_id,
            anatomy,
        )
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

    def _get_current_username(self) -> str:
        if self._current_username is _NOT_SET:
            self._current_username = get_ayon_username()
        return self._current_username

    # --- Workarea ---
    def _reset_file_items(self, task_id: str):
        cache: CacheItem = self._file_items_cache[task_id]
        cache.set_invalid()
        self._file_items_mapping.pop(task_id, None)

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

        cache: CacheItem = self._file_items_cache[task_id]
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

        items = self._host.list_workfiles(
            self._project_name,
            folder_id,
            task_id,
            project_entity=project_entity,
            folder_entity=folder_entity,
            task_entity=task_entity,
            anatomy=anatomy,
            template_key=template_key,
            project_settings=project_settings,
            workfile_entities=workfile_entities,
        )
        cache.update_data(items)

        # Cache items by entity ids and rootless path
        self._file_items_mapping[task_id] = {
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
        self,
        filepaths: list[str],
        file_template: str,
        fill_data: dict[str, Any],
        extensions: set[str]
    ) -> int:
        """

        Todos:
            Validate if logic of this function is correct. It does return
                last version + 1 which might be wrong.

        Args:
            filepaths (list[str]): Workfile paths.
            file_template (str): File template.
            fill_data (dict[str, Any]): Fill data.
            extensions (set[str]): Extensions.

        Returns:
            int: Next workfile version.

        """
        version = get_last_workfile_with_version_from_paths(
            filepaths, file_template, fill_data, extensions
        )[1]
        if version is not None:
            return version + 1

        task_info = fill_data.get("task", {})
        return get_versioning_start(
            self._project_name,
            self._host_name,
            task_name=task_info.get("name"),
            task_type=task_info.get("type"),
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

    def _update_file_description(
        self, task_id: str, rootless_path: str, description: str
    ):
        mapping = self._file_items_mapping.get(task_id)
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
        # TODO create pipeline function for this
        workfile_entities = self.get_workfile_entities(task_id)
        workfile_entity = next(
            (
                _ent
                for _ent in workfile_entities
                if _ent["path"] == rootless_path
            ),
            None
        )
        if not workfile_entity:
            workfile_entity = self._create_workfile_info_entity(
                task_id,
                rootless_path,
                version,
                comment,
                description,
            )
            workfile_entities.append(workfile_entity)
            return

        data = {}
        for key, value in (
            ("host_name", self._host_name),
            ("version", version),
            ("comment", comment),
        ):
            if value is not None:
                data[key] = value

        old_data = workfile_entity["data"]

        changed_data = {}
        for key, value in data.items():
            if key not in old_data or old_data[key] != value:
                changed_data[key] = value

        update_data = {}
        if changed_data:
            update_data["data"] = changed_data

        old_description = workfile_entity["attrib"].get("description")
        if description is not None and old_description != description:
            update_data["attrib"] = {"description": description}
            workfile_entity["attrib"]["description"] = description

        username = self._get_current_username()
        # Automatically fix 'createdBy' and 'updatedBy' fields
        # NOTE both fields were not automatically filled by server
        #   until 1.1.3 release.
        if workfile_entity.get("createdBy") is None:
            update_data["createdBy"] = username
            workfile_entity["createdBy"] = username

        if workfile_entity.get("updatedBy") != username:
            update_data["updatedBy"] = username
            workfile_entity["updatedBy"] = username

        if not update_data:
            return

        session = OperationsSession()
        session.update_entity(
            self._project_name,
            "workfile",
            workfile_entity["id"],
            update_data,
        )
        session.commit()

    def _create_workfile_info_entity(
        self,
        task_id: str,
        rootless_path: str,
        version: Optional[int],
        comment: Optional[str],
        description: str,
    ) -> dict[str, Any]:
        extension = os.path.splitext(rootless_path)[1]

        attrib = {}
        for key, value in (
            ("extension", extension),
            ("description", description),
        ):
            if value is not None:
                attrib[key] = value

        data = {}
        for key, value in (
            ("host_name", self._host_name),
            ("version", version),
            ("comment", comment),
        ):
            if value is not None:
                data[key] = value

        username = self._get_current_username()
        workfile_info = {
            "id": uuid.uuid4().hex,
            "path": rootless_path,
            "taskId": task_id,
            "attrib": attrib,
            "data": data,
            # TODO remove 'createdBy' and 'updatedBy' fields when server is
            #   or above 1.1.3 .
            "createdBy": username,
            "updatedBy": username,
        }

        session = OperationsSession()
        session.create_entity(
            self._project_name, "workfile", workfile_info
        )
        session.commit()
        return workfile_info
