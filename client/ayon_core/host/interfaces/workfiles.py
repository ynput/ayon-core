from __future__ import annotations
import os
import platform
from abc import abstractmethod
from dataclasses import dataclass, asdict
from typing import Optional, Any

import ayon_api


@dataclass
class WorkfileInfo:
    filepath: str
    rootless_path: str
    file_size: Optional[float]
    file_created: Optional[float]
    file_modified: Optional[float]
    workfile_entity_id: Optional[str]
    description: str
    created_by: Optional[str]
    updated_by: Optional[str]
    available: bool

    @classmethod
    def new(cls, filepath, rootless_path, available, workfile_entity):
        file_size = file_modified = file_created = None
        if filepath and os.path.exists(filepath):
            filestat = os.stat(filepath)
            file_size = filestat.st_size
            file_created = filestat.st_ctime
            file_modified = filestat.st_mtime

        if workfile_entity is None:
            workfile_entity = {}

        attrib = {}
        if workfile_entity:
            attrib = workfile_entity["attrib"]

        return cls(
            filepath=filepath,
            rootless_path=rootless_path,
            file_size=file_size,
            file_created=file_created,
            file_modified=file_modified,
            workfile_entity_id=workfile_entity.get("id"),
            description=attrib.get("description") or "",
            created_by=workfile_entity.get("createdBy"),
            updated_by=workfile_entity.get("updatedBy"),
            available=available,
        )

    def to_data(self):
        """Converts file item to data.

        Returns:
            dict[str, Any]: Workfile item data.

        """
        return asdict(self)

    @classmethod
    def from_data(self, data):
        """Converts data to workfile item.

        Args:
            data (dict[str, Any]): Workfile item data.

        Returns:
            WorkfileInfo: File item.

        """
        return WorkfileInfo(**data)


class IWorkfileHost:
    """Implementation requirements to be able use workfile utils and tool."""


    @abstractmethod
    def get_workfile_extensions(self):
        """Extensions that can be used as save.

        Questions:
            This could potentially use 'HostDefinition'.
        """

        return []

    @abstractmethod
    def save_workfile(self, dst_path=None):
        """Save currently opened scene.

        Args:
            dst_path (str): Where the current scene should be saved. Or use
                current path if 'None' is passed.
        """

        pass

    @abstractmethod
    def open_workfile(self, filepath):
        """Open passed filepath in the host.

        Args:
            filepath (str): Path to workfile.
        """

        pass

    @abstractmethod
    def get_current_workfile(self):
        """Retrieve path to current opened file.

        Returns:
            str: Path to file which is currently opened.
            None: If nothing is opened.
        """

        return None

    def workfile_has_unsaved_changes(self):
        """Currently opened scene is saved.

        Not all hosts can know if current scene is saved because the API of
        DCC does not support it.

        Returns:
            bool: True if scene is saved and False if has unsaved
                modifications.
            None: Can't tell if workfiles has modifications.
        """

        return None

    def list_workfiles(
        self,
        project_name: str,
        folder_id: str,
        task_id: str,
        project_entity: Optional[dict[str, Any]] = None,
        folder_entity: Optional[dict[str, Any]] = None,
        task_entity: Optional[dict[str, Any]] = None,
        workfile_entities: Optional[list[dict[str, Any]]] = None,
        template_key: Optional[str] = None,
        project_settings: Optional[dict[str, Any]] = None,
        anatomy: Optional["Anatomy"] = None,
    ) -> list[WorkfileInfo]:
        """List workfiles in the given folder.

        NOTES:
        - Better method name?
        - This method is pre-implemented as the logic can be shared across
            95% of host integrations. Ad-hoc implementation to give host
            integration workfile api functionality.
        - Should this method also handle workfiles based on workfile entities?

        Args:
            project_name (str): Name of project.
            folder_id (str): ID of folder.
            task_id (str): ID of task.
            project_entity (Optional[dict[str, Any]]): Project entity.
            folder_entity (Optional[dict[str, Any]]): Folder entity.
            task_entity (Optional[dict[str, Any]]): Task entity.
            workfile_entities (Optional[list[dict[str, Any]]]): Workfile
                entities.
            template_key (Optional[str]): Template key.
            project_settings (Optional[dict[str, Any]]): Project settings.
            anatomy (Anatomy): Project anatomy.

        Returns:
            list[WorkfileInfo]: List of workfiles.

        """
        from ayon_core.pipeline import Anatomy
        from ayon_core.pipeline.template_data import get_template_data
        from ayon_core.pipeline.workfile import get_workdir_with_workdir_data

        extensions = self.get_workfile_extensions()
        if not extensions:
            return []

        if project_entity is None:
            project_entity = ayon_api.get_project(project_name)

        if folder_entity is None:
            folder_entity = ayon_api.get_folder_by_id(project_name, folder_id)

        if task_entity is None:
            task_entity = ayon_api.get_task_by_id(project_name, task_id)

        if workfile_entities is None:
            workfile_entities = list(ayon_api.get_workfiles_info(
                project_name, task_ids=[task_id]
            ))

        if anatomy is None:
            anatomy = Anatomy(project_name, project_entity=project_entity)

        workfile_entities_by_path = {
            workfile_entity["path"]: workfile_entity
            for workfile_entity in workfile_entities
        }

        workdir_data = get_template_data(
            project_entity,
            folder_entity,
            task_entity,
            host_name=self.name,
        )
        workdir = get_workdir_with_workdir_data(
            workdir_data,
            project_name,
            anatomy=anatomy,
            template_key=template_key,
            project_settings=project_settings,
        )

        if platform.system().lower() == "windows":
            rootless_workdir = workdir.replace("\\", "/")
        else:
            rootless_workdir = workdir

        used_roots = workdir.used_values.get("root")
        if used_roots:
            used_root_name = next(iter(used_roots))
            root_value = used_roots[used_root_name]
            workdir_end = rootless_workdir[len(root_value):].lstrip("/")
            rootless_workdir = f"{{root[{used_root_name}]}}/{workdir_end}"

        filenames = []
        if os.path.exists(workdir):
            filenames = list(os.listdir(workdir))

        items = []
        for filename in filenames:
            filepath = os.path.join(workdir, filename)
            # TODO add 'default' support for folders
            ext = os.path.splitext(filepath)[1].lower()
            if ext not in extensions:
                continue

            rootless_path = f"{rootless_workdir}/{filename}"
            workfile_entity = workfile_entities_by_path.pop(
                rootless_path, None
            )
            items.append(WorkfileInfo.new(
                filepath, rootless_path, True, workfile_entity
            ))

        for workfile_entity in workfile_entities_by_path.values():
            # Workfile entity is not in the filesystem
            #   but it is in the database
            rootless_path = workfile_entity["path"]
            filepath = anatomy.fill_root(rootless_path)
            items.append(WorkfileInfo.new(
                filepath, rootless_path, False, workfile_entity
            ))

        return items

    # --- Deprecated method names ---
    def file_extensions(self):
        """Deprecated variant of 'get_workfile_extensions'.

        Todo:
            Remove when all usages are replaced.
        """
        return self.get_workfile_extensions()

    def save_file(self, dst_path=None):
        """Deprecated variant of 'save_workfile'.

        Todo:
            Remove when all usages are replaced.
        """

        self.save_workfile(dst_path)

    def open_file(self, filepath):
        """Deprecated variant of 'open_workfile'.

        Todo:
            Remove when all usages are replaced.
        """

        return self.open_workfile(filepath)

    def current_file(self):
        """Deprecated variant of 'get_current_workfile'.

        Todo:
            Remove when all usages are replaced.
        """

        return self.get_current_workfile()

    def has_unsaved_changes(self):
        """Deprecated variant of 'workfile_has_unsaved_changes'.

        Todo:
            Remove when all usages are replaced.
        """

        return self.workfile_has_unsaved_changes()
