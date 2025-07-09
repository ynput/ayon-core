from __future__ import annotations

import os
import platform
import shutil
import typing
import warnings
import functools
from abc import abstractmethod
from dataclasses import dataclass, asdict
from typing import Optional, Any

import ayon_api
import arrow

from ayon_core.lib import emit_event
from ayon_core.settings import get_project_settings
from ayon_core.host.constants import ContextChangeReason

if typing.TYPE_CHECKING:
    from ayon_core.pipeline import Anatomy


def deprecated(reason):
    def decorator(func):
        message = f"Call to deprecated function {func.__name__} ({reason})."

        @functools.wraps(func)
        def new_func(*args, **kwargs):
            warnings.simplefilter("always", DeprecationWarning)
            warnings.warn(
                message,
                category=DeprecationWarning,
                stacklevel=2
            )
            warnings.simplefilter("default", DeprecationWarning)
            return func(*args, **kwargs)

        return new_func

    return decorator


# Wrappers for optional arguments that might change in future
class _WorkfileOptionalData:
    """Base class for optional data used in workfile operations."""
    def __init__(
        self,
        *,
        project_entity: Optional[dict[str, Any]] = None,
        anatomy: Optional["Anatomy"] = None,
        project_settings: Optional[dict[str, Any]] = None,
        **kwargs
    ):
        if kwargs:
            cls_name = self.__class__.__name__
            keys = ", ".join(['"{}"'.format(k) for k in kwargs.keys()])
            warnings.warn(
                f"Unknown keywords passed to {cls_name}: {keys}",
            )

        self.project_entity = project_entity
        self.anatomy = anatomy
        self.project_settings = project_settings

    def get_project_data(
        self, project_name: str
    ) -> tuple[dict[str, Any], "Anatomy", dict[str, Any]]:
        from ayon_core.pipeline import Anatomy

        project_entity = self.project_entity
        anatomy = self.anatomy
        project_settings = self.project_settings

        if project_entity is None:
            project_entity = ayon_api.get_project(project_name)

        if anatomy is None:
            anatomy = Anatomy(
                project_name,
                project_entity=project_entity
            )

        if project_settings is None:
            project_settings = get_project_settings(project_name)
        return (
            project_entity,
            anatomy,
            project_settings,
        )


class OpenWorkfileOptionalData(_WorkfileOptionalData):
    """Optional data for opening workfile."""
    data_version = 1


class ListWorkfilesOptionalData(_WorkfileOptionalData):
    """Optional data to list workfiles."""
    data_version = 1

    def __init__(
        self,
        *,
        project_entity: Optional[dict[str, Any]] = None,
        anatomy: Optional["Anatomy"] = None,
        project_settings: Optional[dict[str, Any]] = None,
        template_key: Optional[str] = None,
        workfile_entities: Optional[list[dict[str, Any]]] = None,
        **kwargs
    ):
        super().__init__(
            project_entity=project_entity,
            anatomy=anatomy,
            project_settings=project_settings,
            **kwargs
        )
        self.template_key = template_key
        self.workfile_entities = workfile_entities

    def get_template_key(
        self,
        project_name: str,
        task_type: str,
        host_name: str,
        project_settings: dict[str, Any],
    ) -> str:
        from ayon_core.pipeline.workfile import get_workfile_template_key

        if self.template_key is not None:
            return self.template_key

        return get_workfile_template_key(
            project_name=project_name,
            task_type=task_type,
            host_name=host_name,
            project_settings=project_settings,
        )

    def get_workfile_entities(
        self, project_name: str, task_id: str
    ) -> list[dict[str, Any]]:
        """Fill workfile entities if not provided."""
        if self.workfile_entities is not None:
            return self.workfile_entities
        return list(ayon_api.get_workfiles_info(
            project_name, task_ids=[task_id]
        ))


class ListPublishedWorkfilesOptionalData(_WorkfileOptionalData):
    """Optional data to list published workfiles."""
    data_version = 1

    def __init__(
        self,
        *,
        project_entity: Optional[dict[str, Any]] = None,
        anatomy: Optional["Anatomy"] = None,
        project_settings: Optional[dict[str, Any]] = None,
        product_entities: Optional[list[dict[str, Any]]] = None,
        version_entities: Optional[list[dict[str, Any]]] = None,
        repre_entities: Optional[list[dict[str, Any]]] = None,
        **kwargs
    ):
        super().__init__(
            project_entity=project_entity,
            anatomy=anatomy,
            project_settings=project_settings,
            **kwargs
        )

        self.product_entities = product_entities
        self.version_entities = version_entities
        self.repre_entities = repre_entities

    def get_entities(
        self,
        project_name: str,
        folder_id: str,
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]]
    ]:
        product_entities = self.product_entities
        if product_entities is None:
            product_entities = list(ayon_api.get_products(
                project_name,
                folder_ids={folder_id},
                product_types={"workfile"},
                fields={"id", "name"},
            ))

        version_entities = self.version_entities
        if version_entities is None:
            product_ids = {p["id"] for p in product_entities}
            version_entities = list(ayon_api.get_versions(
                project_name,
                product_ids=product_ids,
                fields={"id", "author", "taskId"},
            ))

        repre_entities = self.repre_entities
        if repre_entities is None:
            version_ids = {v["id"] for v in version_entities}
            repre_entities = list(ayon_api.get_representations(
                project_name,
                version_ids=version_ids,
            ))
        return product_entities, version_entities, repre_entities


class SaveWorkfileOptionalData(_WorkfileOptionalData):
    """Optional data to save workfile."""
    data_version = 1

    def __init__(
        self,
        *,
        project_entity: Optional[dict[str, Any]] = None,
        anatomy: Optional["Anatomy"] = None,
        project_settings: Optional[dict[str, Any]] = None,
        rootless_path: Optional[str] = None,
        workfile_entities: Optional[list[dict[str, Any]]] = None,
        **kwargs
    ):
        super().__init__(
            project_entity=project_entity,
            anatomy=anatomy,
            project_settings=project_settings,
            **kwargs
        )

        self.rootless_path = rootless_path
        self.workfile_entities = workfile_entities

    def get_workfile_entities(self, project_name: str, task_id: str):
        """Fill workfile entities if not provided."""
        if self.workfile_entities is not None:
            return self.workfile_entities
        return list(ayon_api.get_workfiles_info(
            project_name, task_ids=[task_id]
        ))

    def get_rootless_path(
        self,
        workfile_path: str,
        project_name: str,
        folder_entity: dict[str, Any],
        task_entity: dict[str, Any],
        host_name: str,
        project_entity: dict[str, Any],
        project_settings: dict[str, Any],
        anatomy: "Anatomy",
    ):
        from ayon_core.pipeline.workfile.utils import (
            find_workfile_rootless_path
        )

        if self.rootless_path is not None:
            return self.rootless_path

        return find_workfile_rootless_path(
            workfile_path,
            project_name,
            folder_entity,
            task_entity,
            host_name,
            project_entity=project_entity,
            project_settings=project_settings,
            anatomy=anatomy,
        )


class CopyWorkfileOptionalData(SaveWorkfileOptionalData):
    """Optional data to copy workfile."""
    data_version = 1


class CopyPublishedWorkfileOptionalData(SaveWorkfileOptionalData):
    """Optional data to copy published workfile."""
    data_version = 1

    def __init__(
        self,
        project_entity: Optional[dict[str, Any]] = None,
        anatomy: Optional["Anatomy"] = None,
        project_settings: Optional[dict[str, Any]] = None,
        rootless_path: Optional[str] = None,
        workfile_entities: Optional[list[dict[str, Any]]] = None,
        src_anatomy: Optional["Anatomy"] = None,
        src_representation_path: Optional[str] = None,
        **kwargs
    ):
        super().__init__(
            rootless_path=rootless_path,
            workfile_entities=workfile_entities,
            project_entity=project_entity,
            anatomy=anatomy,
            project_settings=project_settings,
            **kwargs
        )
        self.src_anatomy = src_anatomy
        self.src_representation_path = src_representation_path

    def get_source_data(
        self,
        current_anatomy: Optional["Anatomy"],
        project_name: str,
        representation_entity: dict[str, Any],
    ) -> tuple["Anatomy", str]:
        from ayon_core.pipeline import Anatomy
        from ayon_core.pipeline.load import (
            get_representation_path_with_anatomy
        )

        src_anatomy = self.src_anatomy

        if (
            src_anatomy is None
            and current_anatomy is not None
            and current_anatomy.project_name == project_name
        ):
            src_anatomy = current_anatomy
        else:
            src_anatomy = Anatomy(project_name)

        repre_path = self.src_representation_path
        if repre_path is None:
            repre_path = get_representation_path_with_anatomy(
                representation_entity,
                src_anatomy,
            )
        return src_anatomy, repre_path


# Dataclasses used during workfile operations
@dataclass
class OpenWorkfileContext:
    data_version: int
    project_name: str
    filepath: str
    project_entity: dict[str, Any]
    folder_entity: dict[str, Any]
    task_entity: dict[str, Any]
    anatomy: "Anatomy"
    project_settings: dict[str, Any]


@dataclass
class ListWorkfilesContext:
    data_version: int
    project_name: str
    project_entity: dict[str, Any]
    folder_entity: dict[str, Any]
    task_entity: dict[str, Any]
    anatomy: "Anatomy"
    project_settings: dict[str, Any]
    template_key: str
    workfile_entities: list[dict[str, Any]]


@dataclass
class ListPublishedWorkfilesContext:
    data_version: int
    project_name: str
    project_entity: dict[str, Any]
    folder_id: str
    anatomy: "Anatomy"
    project_settings: dict[str, Any]
    product_entities: list[dict[str, Any]]
    version_entities: list[dict[str, Any]]
    repre_entities: list[dict[str, Any]]


@dataclass
class SaveWorkfileContext:
    data_version: int
    project_name: str
    project_entity: dict[str, Any]
    folder_entity: dict[str, Any]
    task_entity: dict[str, Any]
    anatomy: "Anatomy"
    project_settings: dict[str, Any]
    dst_path: str
    rootless_path: str
    workfile_entities: list[dict[str, Any]]


@dataclass
class CopyWorkfileContext(SaveWorkfileContext):
    src_path: str
    version: Optional[int]
    comment: Optional[str]
    description: Optional[str]
    open_workfile: bool


@dataclass
class CopyPublishedWorkfileContext(CopyWorkfileContext):
    src_project_name: str
    src_representation_entity: dict[str, Any]
    src_anatomy: "Anatomy"


def get_open_workfile_context(
    project_name: str,
    filepath: str,
    folder_entity: dict[str, Any],
    task_entity: dict[str, Any],
    prepared_data: Optional[OpenWorkfileOptionalData],
) -> OpenWorkfileContext:
    if prepared_data is None:
        prepared_data = OpenWorkfileOptionalData()
    (
        project_entity, anatomy, project_settings
    ) = prepared_data.get_project_data(project_name)
    return OpenWorkfileContext(
        data_version=prepared_data.data_version,
        filepath=filepath,
        folder_entity=folder_entity,
        task_entity=task_entity,
        project_name=project_name,
        project_entity=project_entity,
        anatomy=anatomy,
        project_settings=project_settings,
    )


def get_list_workfiles_context(
    project_name: str,
    folder_entity: dict[str, Any],
    task_entity: dict[str, Any],
    host_name: str,
    prepared_data: Optional[ListWorkfilesOptionalData],
) -> ListWorkfilesContext:
    if prepared_data is None:
        prepared_data = ListWorkfilesOptionalData()
    (
        project_entity, anatomy, project_settings
    ) = prepared_data.get_project_data(project_name)

    template_key = prepared_data.get_template_key(
        project_name,
        task_entity["taskType"],
        host_name,
        project_settings,
    )
    workfile_entities = prepared_data.get_workfile_entities(
        project_name, task_entity["id"]
    )
    return ListWorkfilesContext(
        data_version=prepared_data.data_version,
        project_entity=project_entity,
        folder_entity=folder_entity,
        task_entity=task_entity,
        project_name=project_name,
        anatomy=anatomy,
        project_settings=project_settings,
        template_key=template_key,
        workfile_entities=workfile_entities,
    )


def get_list_published_workfiles_context(
    project_name: str,
    folder_id: str,
    prepared_data: Optional[ListPublishedWorkfilesOptionalData],
) -> ListPublishedWorkfilesContext:
    if prepared_data is None:
        prepared_data = ListPublishedWorkfilesOptionalData()
    (
        project_entity, anatomy, project_settings
    ) = prepared_data.get_project_data(project_name)
    (
        product_entities,
        version_entities,
        repre_entities,
    ) = prepared_data.get_entities(project_name, folder_id)

    return ListPublishedWorkfilesContext(
        data_version=prepared_data.data_version,
        project_name=project_name,
        project_entity=project_entity,
        folder_id=folder_id,
        anatomy=anatomy,
        project_settings=project_settings,
        product_entities=product_entities,
        version_entities=version_entities,
        repre_entities=repre_entities,
    )


def get_save_workfile_context(
    project_name: str,
    filepath: str,
    folder_entity: dict[str, Any],
    task_entity: dict[str, Any],
    host_name: str,
    prepared_data: Optional[SaveWorkfileOptionalData],
) -> SaveWorkfileContext:
    if prepared_data is None:
        prepared_data = SaveWorkfileOptionalData()

    (
        project_entity, anatomy, project_settings
    ) = prepared_data.get_project_data(project_name)

    rootless_path = prepared_data.get_rootless_path(
        filepath,
        project_name,
        folder_entity,
        task_entity,
        host_name,
        project_entity,
        project_settings,
        anatomy,
    )
    workfile_entities = prepared_data.get_workfile_entities(
        project_name, task_entity["id"]
    )
    return SaveWorkfileContext(
        data_version=prepared_data.data_version,
        project_name=project_name,
        project_entity=project_entity,
        folder_entity=folder_entity,
        task_entity=task_entity,
        anatomy=anatomy,
        project_settings=project_settings,
        dst_path=filepath,
        rootless_path=rootless_path,
        workfile_entities=workfile_entities,
    )


def get_copy_workfile_context(
    project_name: str,
    src_path: str,
    dst_path: str,
    folder_entity: dict[str, Any],
    task_entity: dict[str, Any],
    *,
    version: Optional[int],
    comment: Optional[str],
    description: Optional[str],
    open_workfile: bool,
    host_name: str,
    prepared_data: Optional[CopyWorkfileOptionalData],
) -> CopyWorkfileContext:
    if prepared_data is None:
        prepared_data = CopyWorkfileOptionalData()
    context: SaveWorkfileContext = get_save_workfile_context(
        project_name,
        dst_path,
        folder_entity,
        task_entity,
        host_name,
        prepared_data,
    )
    return CopyWorkfileContext(
        data_version=prepared_data.data_version,
        src_path=src_path,
        project_name=context.project_name,
        project_entity=context.project_entity,
        folder_entity=context.folder_entity,
        task_entity=context.task_entity,
        version=version,
        comment=comment,
        description=description,
        open_workfile=open_workfile,
        anatomy=context.anatomy,
        project_settings=context.project_settings,
        dst_path=context.dst_path,
        rootless_path=context.rootless_path,
        workfile_entities=context.workfile_entities,
    )


def get_copy_repre_workfile_context(
    project_name: str,
    src_project_name: str,
    src_representation_entity: dict[str, Any],
    dst_path: str,
    folder_entity: dict[str, Any],
    task_entity: dict[str, Any],
    version: Optional[int],
    comment: Optional[str],
    description: Optional[str],
    open_workfile: bool,
    host_name: str,
    prepared_data: Optional[CopyPublishedWorkfileOptionalData],
) -> CopyPublishedWorkfileContext:
    if prepared_data is None:
        prepared_data = CopyPublishedWorkfileOptionalData()

    context: SaveWorkfileContext = get_save_workfile_context(
        project_name,
        dst_path,
        folder_entity,
        task_entity,
        host_name,
        prepared_data,
    )
    src_anatomy, repre_path = prepared_data.get_source_data(
        context.anatomy,
        src_project_name,
        src_representation_entity,
    )
    return CopyPublishedWorkfileContext(
        data_version=prepared_data.data_version,
        src_project_name=src_project_name,
        src_representation_entity=src_representation_entity,
        src_path=repre_path,
        dst_path=context.dst_path,
        project_name=context.project_name,
        project_entity=context.project_entity,
        folder_entity=context.folder_entity,
        task_entity=context.task_entity,
        version=version,
        comment=comment,
        description=description,
        open_workfile=open_workfile,
        anatomy=context.anatomy,
        project_settings=context.project_settings,
        rootless_path=context.rootless_path,
        workfile_entities=context.workfile_entities,
        src_anatomy=src_anatomy,
    )


@dataclass
class WorkfileInfo:
    """Information about workfile.

    Host can open, copy and use the workfile using this information object.

    Attributes:
        filepath (str): Path to the workfile.
        rootless_path (str): Path to the workfile without the root. And without
            backslashes on Windows.
        version (Optional[int]): Version of the workfile.
        comment (Optional[str]): Comment of the workfile.
        file_size (Optional[float]): Size of the workfile in bytes.
        file_created (Optional[float]): Timestamp when the workfile was
            created on the filesystem.
        file_modified (Optional[float]): Timestamp when the workfile was
            modified on the filesystem.
        workfile_entity_id (Optional[str]): Workfile entity id. If None then
            the workfile is not in the database.
        description (str): Description of the workfile.
        created_by (Optional[str]): User id of the user who created the
            workfile entity.
        updated_by (Optional[str]): User id of the user who updated the
            workfile entity.
        available (bool): True if workfile is available on the machine.

    """
    filepath: str
    rootless_path: str
    version: Optional[int]
    comment: Optional[str]
    file_size: Optional[float]
    file_created: Optional[float]
    file_modified: Optional[float]
    workfile_entity_id: Optional[str]
    description: str
    created_by: Optional[str]
    updated_by: Optional[str]
    available: bool

    @classmethod
    def new(
        cls,
        filepath: str,
        rootless_path: str,
        *,
        version: Optional[int],
        comment: Optional[str],
        available: bool,
        workfile_entity: dict[str, Any],
    ):
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
            version=version,
            comment=comment,
            file_size=file_size,
            file_created=file_created,
            file_modified=file_modified,
            workfile_entity_id=workfile_entity.get("id"),
            description=attrib.get("description") or "",
            created_by=workfile_entity.get("createdBy"),
            updated_by=workfile_entity.get("updatedBy"),
            available=available,
        )

    def to_data(self) -> dict[str, Any]:
        """Converts file item to data.

        Returns:
            dict[str, Any]: Workfile item data.

        """
        return asdict(self)

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> WorkfileInfo:
        """Converts data to workfile item.

        Args:
            data (dict[str, Any]): Workfile item data.

        Returns:
            WorkfileInfo: File item.

        """
        return WorkfileInfo(**data)


@dataclass
class PublishedWorkfileInfo:
    """Information about published workfile.

    Host can copy and use the workfile using this information object.

    Attributes:
        project_name (str): Name of the project where workfile lives.
        folder_id (str): Folder id under which is workfile stored.
        task_id (Optional[str]): Task id under which is workfile stored.
        representation_id (str): Representation id of the workfile.
        filepath (str): Path to the workfile.
        created_at (float): Timestamp when the workfile representation
            was created.
        author (str): Author of the workfile representation.
        available (bool): True if workfile is available on the machine.
        file_size (Optional[float]): Size of the workfile in bytes.
        file_created (Optional[float]): Timestamp when the workfile was
            created on the filesystem.
        file_modified (Optional[float]): Timestamp when the workfile was
            modified on the filesystem.

    """
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
        *,
        filepath: str,
        author: str,
        available: bool,
        file_size: Optional[float],
        file_modified: Optional[float],
        file_created: Optional[float],
    ) -> "PublishedWorkfileInfo":
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

    def to_data(self) -> dict[str, Any]:
        """Converts file item to data.

        Returns:
            dict[str, Any]: Workfile item data.

        """
        return asdict(self)

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "PublishedWorkfileInfo":
        """Converts data to workfile item.

        Args:
            data (dict[str, Any]): Workfile item data.

        Returns:
            PublishedWorkfileInfo: File item.

        """
        return PublishedWorkfileInfo(**data)


class IWorkfileHost:
    """Implementation requirements to be able to use workfiles utils and tool.

    Some of the methods are pre-implemented as they generally do the same in
        all host integrations.

    """
    @abstractmethod
    def save_workfile(self, dst_path: Optional[str] = None) -> None:
        """Save the currently opened scene.

        Args:
            dst_path (str): Where the current scene should be saved. Or use
                the current path if 'None' is passed.

        """
        pass

    @abstractmethod
    def open_workfile(self, filepath: str) -> None:
        """Open passed filepath in the host.

        Args:
            filepath (str): Path to workfile.

        """
        pass

    @abstractmethod
    def get_current_workfile(self) -> Optional[str]:
        """Retrieve a path to current opened file.

        Returns:
            Optional[str]: Path to the file which is currently opened. None if
                nothing is opened or the current workfile is unsaved.

        """
        return None

    def workfile_has_unsaved_changes(self) -> Optional[bool]:
        """Currently opened scene is saved.

        Not all hosts can know if the current scene is saved because the API
            of DCC does not support it.

        Returns:
            Optional[bool]: True if scene is saved and False if has unsaved
                modifications. None if can't tell if workfiles has
                modifications.

        """
        return None

    def get_workfile_extensions(self) -> list[str]:
        """Extensions that can be used to save the workfile to.

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
        folder_entity: dict[str, Any],
        task_entity: dict[str, Any],
        *,
        version: Optional[int] = None,
        comment: Optional[str] = None,
        description: Optional[str] = None,
        prepared_data: Optional[SaveWorkfileOptionalData] = None,
    ) -> None:
        """Save the current workfile with context.

        Arguments 'rootless_path', 'workfile_entities', 'project_entity'
            and 'anatomy' can be filled to enhance efficiency if you already
            have access to the values.

        Argument 'project_settings' is used to calculate 'rootless_path'
            if it is not provided.

        Notes:
            Should this method care about context change?

        Args:
            filepath (str): Where the current scene should be saved.
            folder_entity (dict[str, Any]): Folder entity.
            task_entity (dict[str, Any]): Task entity.
            version (Optional[int]): Version of the workfile. Information
                for workfile entity. Recommended to fill.
            comment (Optional[str]): Comment for the workfile.
                Usually used in the filename template.
            description (Optional[str]): Artist note for the workfile entity.
            prepared_data (Optional[SaveWorkfileOptionalData]): Prepared data
                for speed enhancements.

        """
        project_name = self.get_current_project_name()
        save_workfile_context = get_save_workfile_context(
            project_name,
            filepath,
            folder_entity,
            task_entity,
            host_name=self.name,
            prepared_data=prepared_data,
        )

        self._before_workfile_save(save_workfile_context)
        event_data = self._get_workfile_event_data(
            project_name,
            folder_entity,
            task_entity,
            filepath,
        )
        self._emit_workfile_save_event(event_data, after_save=False)

        workdir = os.path.dirname(filepath)

        # Set 'AYON_WORKDIR' environment variable
        os.environ["AYON_WORKDIR"] = workdir

        self.set_current_context(
            folder_entity,
            task_entity,
            reason=ContextChangeReason.workfile_save,
            project_entity=save_workfile_context.project_entity,
            anatomy=save_workfile_context.anatomy,
        )

        self.save_workfile(filepath)

        self._save_workfile_entity(
            save_workfile_context,
            version,
            comment,
            description,
        )
        self._after_workfile_save(save_workfile_context)
        self._emit_workfile_save_event(event_data)

    def open_workfile_with_context(
        self,
        filepath: str,
        folder_entity: dict[str, Any],
        task_entity: dict[str, Any],
        *,
        prepared_data: Optional[OpenWorkfileOptionalData] = None,
    ) -> None:
        """Open passed filepath in the host with context.

        This function should be used to open workfile in different context.

        Notes:
            Should this method care about context change?

        Args:
            filepath (str): Path to workfile.
            folder_entity (dict[str, Any]): Folder id.
            task_entity (dict[str, Any]): Task id.
            prepared_data (Optional[WorkfileOptionalData]): Prepared data
                for speed enhancements.

        """
        context = self.get_current_context()
        project_name = context["project_name"]

        open_workfile_context = get_open_workfile_context(
            project_name,
            filepath,
            folder_entity,
            task_entity,
            prepared_data=prepared_data,
        )

        workdir = os.path.dirname(filepath)
        # Set 'AYON_WORKDIR' environment variable
        os.environ["AYON_WORKDIR"] = workdir

        event_data = self._get_workfile_event_data(
            project_name, folder_entity, task_entity, filepath
        )
        self._before_workfile_open(open_workfile_context)
        self._emit_workfile_open_event(event_data, after_open=False)

        self.set_current_context(
            folder_entity,
            task_entity,
            reason=ContextChangeReason.workfile_open,
            project_entity=open_workfile_context.project_entity,
            anatomy=open_workfile_context.anatomy,
        )

        self.open_workfile(filepath)

        self._after_workfile_open(open_workfile_context)
        self._emit_workfile_open_event(event_data)

    def list_workfiles(
        self,
        project_name: str,
        folder_entity: dict[str, Any],
        task_entity: dict[str, Any],
        *,
        prepared_data: Optional[ListWorkfilesOptionalData] = None,
    ) -> list[WorkfileInfo]:
        """List workfiles in the given task.

        The method should also return workfiles that are not available on
            disk, but are in the AYON database.

        Notes:
        - Better method name?
        - This method is pre-implemented as the logic can be shared across
            95% of host integrations. Ad-hoc implementation to give host
            integration workfile api functionality.

        Args:
            project_name (str): Project name.
            folder_entity (dict[str, Any]): Folder entity.
            task_entity (dict[str, Any]): Task entity.
            prepared_data (Optional[ListWorkfilesOptionalData]): Prepared
                data for speed enhancements.

        Returns:
            list[WorkfileInfo]: List of workfiles.

        """
        from ayon_core.pipeline.template_data import get_template_data
        from ayon_core.pipeline.workfile.path_resolving import (
            get_workdir_with_workdir_data,
            WorkfileDataParser,
        )

        extensions = self.get_workfile_extensions()
        if not extensions:
            return []

        list_workfiles_context = get_list_workfiles_context(
            project_name,
            folder_entity,
            task_entity,
            host_name=self.name,
            prepared_data=prepared_data,
        )

        workfile_entities_by_path = {
            workfile_entity["path"]: workfile_entity
            for workfile_entity in list_workfiles_context.workfile_entities
        }

        workdir_data = get_template_data(
            list_workfiles_context.project_entity,
            folder_entity,
            task_entity,
            host_name=self.name,
        )
        workdir = get_workdir_with_workdir_data(
            workdir_data,
            project_name,
            anatomy=list_workfiles_context.anatomy,
            template_key=list_workfiles_context.template_key,
            project_settings=list_workfiles_context.project_settings,
        )

        file_template = list_workfiles_context.anatomy.get_template_item(
            "work", list_workfiles_context.template_key, "file"
        )
        rootless_workdir = workdir.rootless
        if platform.system().lower() == "windows":
            rootless_workdir = rootless_workdir.replace("\\", "/")

        filenames = []
        if os.path.exists(workdir):
            filenames = list(os.listdir(workdir))

        data_parser = WorkfileDataParser(file_template, workdir_data)
        items = []
        for filename in filenames:
            # TODO add 'default' support for folders
            ext = os.path.splitext(filename)[1].lower()
            if ext not in extensions:
                continue

            filepath = os.path.join(workdir, filename)

            rootless_path = f"{rootless_workdir}/{filename}"
            # Double slashes can happen when root leads to root of disk or
            #   when task exists on root folder
            #   - '/{hierarchy}/{folder[name]}' -> '//some_folder'
            while "//" in rootless_path:
                rootless_path = rootless_path.replace("//", "/")
            workfile_entity = workfile_entities_by_path.pop(
                rootless_path, None
            )
            version = comment = None
            if workfile_entity:
                _data = workfile_entity["data"]
                version = _data.get("version")
                comment = _data.get("comment")

            if version is None:
                parsed_data = data_parser.parse_data(filename)
                version = parsed_data.version
                comment = parsed_data.comment

            item = WorkfileInfo.new(
                filepath,
                rootless_path,
                version=version,
                comment=comment,
                available=True,
                workfile_entity=workfile_entity,
            )
            items.append(item)

        for workfile_entity in workfile_entities_by_path.values():
            # Workfile entity is not in the filesystem
            #   but it is in the database
            rootless_path = workfile_entity["path"]
            ext = os.path.splitext(rootless_path)[1].lower()
            if ext not in extensions:
                continue

            _data = workfile_entity["data"]
            version = _data.get("version")
            comment = _data.get("comment")
            if version is None:
                filename = os.path.basename(rootless_path)
                parsed_data = data_parser.parse_data(filename)
                version = parsed_data.version
                comment = parsed_data.comment

            filepath = list_workfiles_context.anatomy.fill_root(rootless_path)
            items.append(WorkfileInfo.new(
                filepath,
                rootless_path,
                version=version,
                comment=comment,
                available=False,
                workfile_entity=workfile_entity,
            ))

        return items

    def list_published_workfiles(
        self,
        project_name: str,
        folder_id: str,
        *,
        prepared_data: Optional[ListPublishedWorkfilesOptionalData] = None,
    ) -> list[PublishedWorkfileInfo]:
        """List published workfiles for the given folder.

        The default implementation looks for products with the 'workfile'
            product type.

        Pre-fetched entities have mandatory fields to be fetched:
            - Version: 'id', 'author', 'taskId'
            - Representation: 'id', 'versionId', 'files'

        Args:
            project_name (str): Project name.
            folder_id (str): Folder id.
            prepared_data (Optional[ListPublishedWorkfilesOptionalData]):
                Prepared data for speed enhancements.

        Returns:
            list[PublishedWorkfileInfo]: Published workfile information for
                the given context.

        """
        list_workfiles_context = get_list_published_workfiles_context(
            project_name,
            folder_id,
            prepared_data=prepared_data,
        )
        if not list_workfiles_context.repre_entities:
            return []

        versions_by_id = {
            version_entity["id"]: version_entity
            for version_entity in list_workfiles_context.version_entities
        }
        extensions = {
            ext.lstrip(".")
            for ext in self.get_workfile_extensions()
        }
        items = []
        for repre_entity in list_workfiles_context.repre_entities:
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
                workfile_path = workfile_path.format(
                    root=list_workfiles_context.anatomy.roots
                )
            except Exception:
                self.log.warning(
                    "Failed to format workfile path.", exc_info=True
                )

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
                filepath=workfile_path,
                author=version_entity["author"],
                available=is_available,
                file_size=file_size,
                file_created=file_created,
                file_modified=file_modified,
            )
            items.append(workfile_item)

        return items

    def copy_workfile(
        self,
        src_path: str,
        dst_path: str,
        folder_entity: dict[str, Any],
        task_entity: dict[str, Any],
        *,
        version: Optional[int] = None,
        comment: Optional[str] = None,
        description: Optional[str] = None,
        open_workfile: bool = True,
        prepared_data: Optional[CopyWorkfileOptionalData] = None,
    ) -> None:
        """Save workfile path with target folder and task context.

        It is expected that workfile is saved to the current project, but
            can be copied from the other project.

        Arguments 'rootless_path', 'workfile_entities', 'project_entity'
            and 'anatomy' can be filled to enhance efficiency if you already
            have access to the values.

        Argument 'project_settings' is used to calculate 'rootless_path'
            if it is not provided.

        Args:
            src_path (str): Path to the source scene.
            dst_path (str): Where the scene should be saved.
            folder_entity (dict[str, Any]): Folder entity.
            task_entity (dict[str, Any]): Task entity.
            version (Optional[int]): Version of the workfile. Information
                for workfile entity. Recommended to fill.
            comment (Optional[str]): Comment for the workfile.
            description (Optional[str]): Artist note for the workfile entity.
            open_workfile (bool): Open workfile when copied.
            prepared_data (Optional[CopyWorkfileOptionalData]): Prepared data
                for speed enhancements.

        """
        project_name = self.get_current_project_name()
        copy_workfile_context: CopyWorkfileContext = get_copy_workfile_context(
            project_name,
            src_path,
            dst_path,
            folder_entity,
            task_entity,
            version=version,
            comment=comment,
            description=description,
            open_workfile=open_workfile,
            host_name=self.name,
            prepared_data=prepared_data,
        )
        self._copy_workfile(
            copy_workfile_context,
            version=version,
            comment=comment,
            description=description,
            open_workfile=open_workfile,
        )

    def copy_workfile_representation(
        self,
        src_project_name: str,
        src_representation_entity: dict[str, Any],
        dst_path: str,
        folder_entity: dict[str, Any],
        task_entity: dict[str, Any],
        *,
        version: Optional[int] = None,
        comment: Optional[str] = None,
        description: Optional[str] = None,
        open_workfile: bool = True,
        prepared_data: Optional[CopyPublishedWorkfileOptionalData] = None,
    ) -> None:
        """Copy workfile representation.

        Use representation as a source for the workfile.

        Arguments 'rootless_path', 'workfile_entities', 'project_entity'
            and 'anatomy' can be filled to enhance efficiency if you already
            have access to the values.

        Argument 'project_settings' is used to calculate 'rootless_path'
            if it is not provided.

        Args:
            src_project_name (str): Project name.
            src_representation_entity (dict[str, Any]): Representation
                entity.
            dst_path (str): Where the scene should be saved.
            folder_entity (dict[str, Any): Folder entity.
            task_entity (dict[str, Any]): Task entity.
            version (Optional[int]): Version of the workfile. Information
                for workfile entity. Recommended to fill.
            comment (Optional[str]): Comment for the workfile.
            description (Optional[str]): Artist note for the workfile entity.
            open_workfile (bool): Open workfile when copied.
            prepared_data (Optional[CopyPublishedWorkfileOptionalData]):
                Prepared data for speed enhancements.

        """
        project_name = self.get_current_project_name()
        copy_repre_workfile_context: CopyPublishedWorkfileContext = (
            get_copy_repre_workfile_context(
                project_name,
                src_project_name,
                src_representation_entity,
                dst_path,
                folder_entity,
                task_entity,
                version=version,
                comment=comment,
                description=description,
                open_workfile=open_workfile,
                host_name=self.name,
                prepared_data=prepared_data,
            )
        )
        self._copy_workfile(
            copy_repre_workfile_context,
            version=version,
            comment=comment,
            description=description,
            open_workfile=open_workfile,
        )

    # --- Deprecated method names ---
    @deprecated("Use 'get_workfile_extensions' instead")
    def file_extensions(self):
        """Deprecated variant of 'get_workfile_extensions'.

        Todo:
            Remove when all usages are replaced.

        """
        return self.get_workfile_extensions()

    @deprecated("Use 'save_workfile' instead")
    def save_file(self, dst_path=None):
        """Deprecated variant of 'save_workfile'.

        Todo:
            Remove when all usages are replaced

        """
        self.save_workfile(dst_path)

    @deprecated("Use 'open_workfile' instead")
    def open_file(self, filepath):
        """Deprecated variant of 'open_workfile'.

        Todo:
            Remove when all usages are replaced.

        """
        return self.open_workfile(filepath)

    @deprecated("Use 'get_current_workfile' instead")
    def current_file(self):
        """Deprecated variant of 'get_current_workfile'.

        Todo:
            Remove when all usages are replaced.

        """
        return self.get_current_workfile()

    @deprecated("Use 'workfile_has_unsaved_changes' instead")
    def has_unsaved_changes(self):
        """Deprecated variant of 'workfile_has_unsaved_changes'.

        Todo:
            Remove when all usages are replaced.

        """
        return self.workfile_has_unsaved_changes()

    def _copy_workfile(
        self,
        copy_workfile_context: CopyWorkfileContext,
        *,
        version: Optional[int],
        comment: Optional[str],
        description: Optional[str],
        open_workfile: bool,
    ) -> None:
        """Save workfile path with target folder and task context.

        It is expected that workfile is saved to the current project, but
            can be copied from the other project.

        Arguments 'rootless_path', 'workfile_entities', 'project_entity'
            and 'anatomy' can be filled to enhance efficiency if you already
            have access to the values.

        Argument 'project_settings' is used to calculate 'rootless_path'
            if it is not provided.

        Args:
            copy_workfile_context (CopyWorkfileContext): Prepared data
                for speed enhancements.
            version (Optional[int]): Version of the workfile. Information
                for workfile entity. Recommended to fill.
            comment (Optional[str]): Comment for the workfile.
            description (Optional[str]): Artist note for the workfile entity.
            open_workfile (bool): Open workfile when copied.

        """
        self._before_workfile_copy(copy_workfile_context)
        event_data = self._get_workfile_event_data(
            copy_workfile_context.project_name,
            copy_workfile_context.folder_entity,
            copy_workfile_context.task_entity,
            copy_workfile_context.dst_path,
        )
        self._emit_workfile_save_event(event_data, after_save=False)

        dst_dir = os.path.dirname(copy_workfile_context.dst_path)
        if not os.path.exists(dst_dir):
            os.makedirs(dst_dir, exist_ok=True)
        shutil.copy(
            copy_workfile_context.src_path,
            copy_workfile_context.dst_path
        )

        self._save_workfile_entity(
            copy_workfile_context,
            version,
            comment,
            description,
        )
        self._after_workfile_copy(copy_workfile_context)
        self._emit_workfile_save_event(event_data)

        if not open_workfile:
            return

        self.open_workfile_with_context(
            copy_workfile_context.dst_path,
            copy_workfile_context.folder_entity,
            copy_workfile_context.task_entity,
        )

    def _save_workfile_entity(
        self,
        save_workfile_context: SaveWorkfileContext,
        version: Optional[int],
        comment: Optional[str],
        description: Optional[str],
    ) -> Optional[dict[str, Any]]:
        """Create of update workfile entity to AYON based on provided data.

        Args:
            save_workfile_context (SaveWorkfileContext): Save workfile
                context with all prepared data.
            version (Optional[int]): Version of the workfile.
            comment (Optional[str]): Comment for the workfile.
            description (Optional[str]): Artist note for the workfile entity.

        Returns:
            Optional[dict[str, Any]]: Workfile entity.

        """
        from ayon_core.pipeline.workfile.utils import (
            save_workfile_info
        )

        project_name = self.get_current_project_name()
        if not description:
            description = None

        if not comment:
            comment = None

        rootless_path = save_workfile_context.rootless_path
        # It is not possible to create workfile infor without rootless path
        workfile_info = None
        if not rootless_path:
            return workfile_info

        if platform.system().lower() == "windows":
            rootless_path = rootless_path.replace("\\", "/")

        workfile_info = save_workfile_info(
            project_name,
            save_workfile_context.task_entity["id"],
            rootless_path,
            self.name,
            version,
            comment,
            description,
            workfile_entities=save_workfile_context.workfile_entities,
        )
        return workfile_info

    def _create_extra_folders(
        self,
        folder_entity: dict[str, Any],
        task_entity: dict[str, Any],
        workdir: str,
    ) -> None:
        """Create extra folders in the workdir.

        This method should be called when workfile is saved or copied.

        Args:
            folder_entity (dict[str, Any]): Folder entity.
            task_entity (dict[str, Any]): Task entity.
            workdir (str): Workdir where workfile/s will be stored.

        """
        from ayon_core.pipeline.workfile.path_resolving import (
            create_workdir_extra_folders
        )

        project_name = self.get_current_project_name()

        # Create extra folders
        create_workdir_extra_folders(
            workdir,
            self.name,
            task_entity["taskType"],
            task_entity["name"],
            project_name
        )

    def _get_workfile_event_data(
        self,
        project_name: str,
        folder_entity: dict[str, Any],
        task_entity: dict[str, Any],
        filepath: str,
    ) -> dict[str, Optional[str]]:
        """Prepare workfile event data.

        Args:
            project_name (str): Name of the project where workfile lives.
            folder_entity (dict[str, Any]): Folder entity.
            task_entity (dict[str, Any]): Task entity.
            filepath (str): Path to the workfile.

        Returns:
            dict[str, Optional[str]]: Data for workfile event.

        """
        workdir, filename = os.path.split(filepath)
        return {
            "project_name": project_name,
            "folder_id": folder_entity["id"],
            "folder_path": folder_entity["path"],
            "task_id": task_entity["id"],
            "task_name": task_entity["name"],
            "host_name": self.name,
            "filepath": filepath,
            "filename": filename,
            "workdir_path": workdir,
        }

    def _before_workfile_open(
        self, open_workfile_context: OpenWorkfileContext
    ) -> None:
        """Before workfile is opened.

        This method is called before the workfile is opened in the host.

        Can be overridden to implement host specific logic.

        Args:
            open_workfile_context (OpenWorkfileContext): Context and path of
                workfile to open.

        """
        pass

    def _after_workfile_open(
        self, open_workfile_context: OpenWorkfileContext
    ) -> None:
        """After workfile is opened.

        This method is called after the workfile is opened in the host.

        Can be overridden to implement host specific logic.

        Args:
            open_workfile_context (OpenWorkfileContext): Context and path of
                opened workfile.

        """
        pass

    def _before_workfile_save(
        self, save_workfile_context: SaveWorkfileContext
    ) -> None:
        """Before workfile is saved.

        This method is called before the workfile is saved in the host.

        Can be overridden to implement host specific logic.

        Args:
            save_workfile_context (SaveWorkfileContext): Workfile path with
                target folder and task context.

        """
        pass

    def _after_workfile_save(
        self, save_workfile_context: SaveWorkfileContext
    ) -> None:
        """After workfile is saved.

        This method is called after the workfile is saved in the host.

        Can be overridden to implement host specific logic.

        Args:
            save_workfile_context (SaveWorkfileContext): Workfile path with
                target folder and task context.

        """
        workdir = os.path.dirname(save_workfile_context.dst_path)
        self._create_extra_folders(
            save_workfile_context.folder_entity,
            save_workfile_context.task_entity,
            workdir
        )

    def _before_workfile_copy(
        self, copy_workfile_context: CopyWorkfileContext
    ) -> None:
        """Before workfile is copied.

        This method is called before the workfile is copied by host
            integration.

        Can be overridden to implement host specific logic.

        Args:
            copy_workfile_context (CopyWorkfileContext): Source and destination
                path with context before workfile is copied.

        """
        pass

    def _after_workfile_copy(
        self, copy_workfile_context: CopyWorkfileContext
    ) -> None:
        """After workfile is copied.

        This method is called after the workfile is copied by host
            integration.

        Can be overridden to implement host specific logic.

        Args:
            copy_workfile_context (CopyWorkfileContext): Source and destination
                path with context after workfile is copied.

        """
        workdir = os.path.dirname(copy_workfile_context.dst_path)
        self._create_extra_folders(
            copy_workfile_context.folder_entity,
            copy_workfile_context.task_entity,
            workdir,
        )

    def _emit_workfile_open_event(
        self,
        event_data: dict[str, Optional[str]],
        after_open: bool = True,
    ) -> None:
        """Emit workfile save event.

        Emit event before and after workfile is opened.

        This method is not meant to be overridden.

        Other addons can listen to this event and do additional steps.

        Args:
            event_data (dict[str, Optional[str]]): Prepare event data.
            after_open (bool): Emit event after workfile is opened.

        """
        topics = []
        topic_end = "before"
        if after_open:
            topics.append("workfile.opened")
            topic_end = "after"

        # Keep backwards compatible event topic
        topics.append(f"workfile.open.{topic_end}")

        for topic in topics:
            emit_event(topic, event_data)

    def _emit_workfile_save_event(
        self,
        event_data: dict[str, Optional[str]],
        after_save: bool = True,
    ) -> None:
        """Emit workfile save event.

        Emit event before and after workfile is saved or copied.

        This method is not meant to be overridden.

        Other addons can listen to this event and do additional steps.

        Args:
            event_data (dict[str, Optional[str]]): Prepare event data.
            after_save (bool): Emit event after workfile is saved.

        """
        topics = []
        topic_end = "before"
        if after_save:
            topics.append("workfile.saved")
            topic_end = "after"

        # Keep backwards compatible event topic
        topics.append(f"workfile.save.{topic_end}")

        for topic in topics:
            emit_event(topic, event_data)
