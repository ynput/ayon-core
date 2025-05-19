from __future__ import annotations
import os
import platform
import shutil
from abc import abstractmethod
from dataclasses import dataclass, asdict
import typing
from typing import Optional, Any

import ayon_api
import arrow

if typing.TYPE_CHECKING:
    from ayon_core.pipeline import Anatomy


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
    def from_data(cls, data):
        """Converts data to workfile item.

        Args:
            data (dict[str, Any]): Workfile item data.

        Returns:
            WorkfileInfo: File item.

        """
        return WorkfileInfo(**data)


@dataclass
class PublishedWorkfileInfo:
    project_name: str
    folder_id: str
    task_id: Optional[str]
    representation_id: str
    filepath: str
    created_at: float
    author: str
    available: bool
    file_size: Optional[float]
    file_created: Optional[float]
    file_modified: Optional[float]

    @classmethod
    def new(
        cls,
        project_name: str,
        folder_id: str,
        task_id: Optional[str],
        repre_entity: dict[str, Any],
        filepath: str,
        author: str,
        available: bool,
        file_size: Optional[float],
        file_modified: Optional[float],
        file_created: Optional[float],
    ):
        created_at = arrow.get(repre_entity["createdAt"]).to("local")

        return cls(
            project_name=project_name,
            folder_id=folder_id,
            task_id=task_id,
            representation_id=repre_entity["id"],
            filepath=filepath,
            created_at=created_at.float_timestamp,
            author=author,
            available=available,
            file_size=file_size,
            file_created=file_created,
            file_modified=file_modified,
        )

    def to_data(self):
        """Converts file item to data.

        Returns:
            dict[str, Any]: Workfile item data.

        """
        return asdict(self)

    @classmethod
    def from_data(cls, data):
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
    def save_workfile(self, dst_path: Optional[str] = None):
        """Save currently opened scene.

        Args:
            dst_path (str): Where the current scene should be saved. Or use
                current path if 'None' is passed.

        """
        pass

    @abstractmethod
    def open_workfile(self, filepath: str):
        """Open passed filepath in the host.

        Args:
            filepath (str): Path to workfile.

        """
        pass

    @abstractmethod
    def get_current_workfile(self) -> Optional[str]:
        """Retrieve path to current opened file.

        Returns:
            Optional[str]: Path to file which is currently opened. None if
                nothing is opened.

        """
        return None

    def workfile_has_unsaved_changes(self) -> Optional[bool]:
        """Currently opened scene is saved.

        Not all hosts can know if current scene is saved because the API of
        DCC does not support it.

        Returns:
            Optional[bool]: True if scene is saved and False if has unsaved
                modifications. None if can't tell if workfiles has
                modifications.

        """
        return None

    def get_workfile_extensions(self) -> list[str]:
        """Extensions that can be used as save workfile.

        Notes:
            Method may not be used if 'list_workfiles' and
                'list_published_workfiles' are re-implemented with different
                logic.

        Returns:
            list[str]: List of extensions that can be used for saving.

        """
        return []

    def save_workfile_with_context(
        self,
        filepath: str,
        folder_entity: dict[str, Any] = None,
        task_entity: dict[str, Any] = None,
    ):
        """Save current workfile with context.

        Notes:
            Should this method care about context change?

        Args:
            filepath (str): Where the current scene should be saved.
            folder_entity (dict[str, Any]): Folder entity.
            task_entity (dict[str, Any]): Task entity.

        """
        self.save_workfile(filepath)

    def open_workfile_with_context(
        self,
        filepath: str,
        folder_entity: dict[str, Any],
        task_entity: dict[str, Any],
    ):
        """Open passed filepath in the host with context.

        This function should be used to open workfile in different context.

        Notes:
            Should this method care about context change?

        Args:
            filepath (str): Path to workfile.
            folder_id (str): Folder id.
            task_id (str): Task id.

        """
        self.open_workfile(filepath)


    def list_workfiles(
        self,
        project_name: str,
        folder_entity: dict[str, Any],
        task_entity: dict[str, Any],
        project_entity: Optional[dict[str, Any]] = None,
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
            folder_entity (dict[str, Any]): Folder entity.
            task_entity (dict[str, Any]): Task entity.
            project_entity (Optional[dict[str, Any]]): Project entity.
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

        if workfile_entities is None:
            task_id = task_entity["id"]
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

    def list_published_workfiles(
        self,
        project_name: str,
        folder_id: str,
        anatomy: Optional["Anatomy"] = None,
        version_entities: Optional[list[dict[str, Any]]] = None,
        repre_entities: Optional[list[dict[str, Any]]] = None,
    ) -> list[PublishedWorkfileInfo]:
        """List published workfiles for given folder.

        Default implementation looks for products with 'workfile'
            product type.

        Pre-fetched entities have mandatory fields to be fetched.
         -  Version: 'id', 'author', 'taskId'
         -  Representation: 'id', 'versionId', 'files'

        Args:
            project_name (str): Project name.
            folder_id (str): Folder id.
            anatomy (Anatomy): Project anatomy.
            version_entities (Optional[list[dict[str, Any]]]): Pre-fetched
                version entities.
            repre_entities (Optional[list[dict[str, Any]]]): Pre-fetched
                representation entities.

        Returns:
            list[PublishedWorkfileInfo]: Published workfile information for
                given context.

        """
        from ayon_core.pipeline import Anatomy

        # Get all representations of the folder
        (
            version_entities,
            repre_entities
        ) = self._fetch_workfile_entities(
            project_name,
            folder_id,
            version_entities,
            repre_entities,
        )
        if not repre_entities:
            return []

        if anatomy is None:
            anatomy = Anatomy(project_name)

        versions_by_id = {
            version_entity["id"]: version_entity
            for version_entity in version_entities
        }
        extensions = {
            ext.lstrip(".")
            for ext in self.get_workfile_extensions()
        }
        items = []
        for repre_entity in repre_entities:
            version_id = repre_entity["versionId"]
            version_entity = versions_by_id[version_id]
            task_id = version_entity["taskId"]

            # Filter by extension
            workfile_path = None
            for repre_file in repre_entity["files"]:
                ext = (
                    os.path.splitext(repre_file["name"])[1]
                    .lower()
                    .lstrip(".")
                )
                if ext in extensions:
                    workfile_path = repre_file["path"]
                    break

            if not workfile_path:
                continue

            try:
                workfile_path = workfile_path.format(root=anatomy.roots)
            except Exception as exc:
                print(f"Failed to format workfile path: {exc}")

            is_available = False
            file_size = file_modified = file_created = None
            if workfile_path and os.path.exists(workfile_path):
                filestat = os.stat(workfile_path)
                is_available = True
                file_size = filestat.st_size
                file_created = filestat.st_ctime
                file_modified = filestat.st_mtime

            workfile_item = PublishedWorkfileInfo.new(
                project_name,
                folder_id,
                task_id,
                repre_entity,
                workfile_path,
                version_entity["author"],
                is_available,
                file_size,
                file_created,
                file_modified,
            )
            items.append(workfile_item)

        return items

    def copy_workfile(
        self,
        src_path: str,
        dst_path: str,
        folder_entity: dict[str, Any],
        task_entity: dict[str, Any],
        open_workfile: bool = False,
    ):
        """Save workfile path with target folder and task context.

        It is expected that workfile is saved to current project, but can be
            copied from other project.

        Args:
            src_path (str): Path to the source scene.
            dst_path (str): Where the scene should be saved.
            folder_entity (dict[str, Any]): Folder entity.
            task_entity (dict[str, Any]): Task entity.
            open_workfile (bool): Open workfile when copied.

        """
        # TODO We might need option to open file once copied as some DCC might
        #   actually need to open the workfile to copy it.
        dst_dir = os.path.dirname(dst_path)
        if not os.path.exists(dst_dir):
            os.makedirs(dst_dir, exist_ok=True)
        shutil.copy(src_path, dst_path)
        if open_workfile:
            self.open_workfile_with_context(
                dst_path,
                folder_entity,
                task_entity,
            )

    def copy_workfile_representation(
        self,
        src_project_name: str,
        src_representation_entity: dict[str, Any],
        dst_path: str,
        folder_entity: dict[str, Any],
        task_entity: dict[str, Any],
        open_workfile: bool = False,
        anatomy: Optional[Anatomy] = None,
        src_representation_path: Optional[str] = None,
    ):
        """Copy workfile representation.

        Use representation as source for the workfile.

        Args:
            src_project_name (str): Project name.
            src_representation_entity (dict[str, Any]): Representation
                entity.
            dst_path (str): Where the scene should be saved.
            folder_entity (dict[str, Any): Folder entity.
            task_entity (dict[str, Any]): Task entity.
            open_workfile (bool): Open workfile when copied.
            anatomy (Optional[Anatomy]): Project anatomy.
            src_representation_path (Optional[str]): Representation path.

        """
        # TODO We might need option to open file once copied as some DCC might
        #   actually need to open the workfile to copy it.
        from ayon_core.pipeline import Anatomy
        from ayon_core.pipeline.load import (
            get_representation_path_with_anatomy
        )

        if src_representation_path is None:
            if anatomy is None:
                anatomy = Anatomy(src_project_name)
            src_representation_path = get_representation_path_with_anatomy(
                src_representation_entity,
                anatomy,
            )

        self.copy_workfile(
            src_representation_path,
            dst_path,
            folder_entity,
            task_entity,
            open_workfile=open_workfile,
        )

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

    def _fetch_workfile_entities(
        self,
        project_name: str,
        folder_id: str,
        version_entities: Optional[list[dict[str, Any]]],
        repre_entities: Optional[list[dict[str, Any]]],
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]]
    ]:
        if repre_entities is not None and version_entities is None:
            # Get versions of representations
            version_ids = {r["versionId"] for r in repre_entities}
            version_entities = list(ayon_api.get_versions(
                project_name,
                version_ids=version_ids,
                fields={"id", "author", "taskId"},
            ))

        if version_entities is None:
            # Get product entities of folder
            product_entities = ayon_api.get_products(
                project_name,
                folder_ids={folder_id},
                product_types={"workfile"},
                fields={"id", "name"}
            )

            version_entities = []
            product_ids = {product["id"] for product in product_entities}
            if product_ids:
                # Get version docs of products with their families
                version_entities = list(ayon_api.get_versions(
                    project_name,
                    product_ids=product_ids,
                    fields={"id", "author", "taskId"},
                ))

        # Fetch representations of filtered versions and add filter for
        #   extension
        if repre_entities is None:
            repre_entities = []
            if version_entities:
                repre_entities = list(ayon_api.get_representations(
                    project_name,
                    version_ids={v["id"] for v in version_entities}
                ))

        return version_entities, repre_entities
