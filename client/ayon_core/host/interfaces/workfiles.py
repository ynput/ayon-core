import os
from abc import abstractmethod
from dataclasses import dataclass, asdict
from typing import Optional


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
