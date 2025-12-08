from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
import typing
from typing import Optional, Any

from .constants import ContextChangeReason

if typing.TYPE_CHECKING:
    from ayon_core.pipeline import Anatomy

    from .typing import HostContextData


@dataclass
class ApplicationInformation:
    """Application information.

    Attributes:
        app_name (Optional[str]): Application name. e.g. Maya, NukeX, Nuke
        app_version (Optional[str]): Application version. e.g. 15.2.1

    """
    app_name: Optional[str] = None
    app_version: Optional[str] = None


class AbstractHost(ABC):
    """Abstract definition of host implementation."""
    @property
    @abstractmethod
    def log(self) -> logging.Logger:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Host name."""
        pass

    @abstractmethod
    def get_app_information(self) -> ApplicationInformation:
        """Information about the application where host is running.

        Returns:
            ApplicationInformation: Application information.

        """
        pass

    @abstractmethod
    def get_current_context(self) -> HostContextData:
        """Get the current context of the host.

        Current context is defined by project name, folder path and task name.

        Returns:
            HostContextData: The current context of the host.

        """
        pass

    @abstractmethod
    def set_current_context(
        self,
        folder_entity: dict[str, Any],
        task_entity: dict[str, Any],
        *,
        reason: ContextChangeReason = ContextChangeReason.undefined,
        project_entity: Optional[dict[str, Any]] = None,
        anatomy: Optional[Anatomy] = None,
    ) -> HostContextData:
        """Change context of the host.

        Args:
            folder_entity (dict[str, Any]): Folder entity.
            task_entity (dict[str, Any]): Task entity.
            reason (ContextChangeReason): Reason for change.
            project_entity (dict[str, Any]): Project entity.
            anatomy (Anatomy): Anatomy entity.

        """
        pass

    @abstractmethod
    def get_current_project_name(self) -> str:
        """Get the current project name.

        Returns:
            Optional[str]: The current project name.

        """
        pass

    @abstractmethod
    def get_current_folder_path(self) -> Optional[str]:
        """Get the current folder path.

        Returns:
            Optional[str]: The current folder path.

        """
        pass

    @abstractmethod
    def get_current_task_name(self) -> Optional[str]:
        """Get the current task name.

        Returns:
            Optional[str]: The current task name.

        """
        pass

    @abstractmethod
    def get_context_title(self) -> str:
        """Get the context title used in UIs."""
        pass
