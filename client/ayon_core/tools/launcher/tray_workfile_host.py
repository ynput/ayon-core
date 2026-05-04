"""IWorkfileHost stub for tray/launcher flows without a live DCC scene.

Used only as a vehicle to call ``IWorkfileHost.list_published_workfiles`` from
``WorkfilesModel._get_published_workfile_items``. Opening a published file
locally (temp copy, no new workfile version) is handled separately by
``launcher_open_publish`` and ``BaseLauncherController.open_published_representation_local``.
"""

from __future__ import annotations

from typing import Any, Optional

from ayon_core.host import IWorkfileHost
from ayon_core.host.abstract import ApplicationInformation
from ayon_core.host.host import HostBase


class TrayWorkfileHost(HostBase, IWorkfileHost):
    """Minimal IWorkfileHost for the tray launcher (no live DCC scene).

    Provides project name and workfile extensions so the base-class
    ``list_published_workfiles`` can filter and resolve representations.
    All other workfile operations are either no-ops or raise.
    """

    def __init__(self, launcher_controller: Any) -> None:
        super().__init__()
        self._launcher = launcher_controller

    @property
    def name(self) -> str:
        return "launcher"

    def get_app_information(self) -> ApplicationInformation:
        return ApplicationInformation(app_name="AYON Launcher")

    def get_current_project_name(self) -> str:
        return self._launcher.get_selected_project_name() or ""

    def get_workfile_extensions(self) -> list[str]:
        return self._launcher.get_tray_workfile_extensions()

    # --- required abstract stubs ---

    def save_workfile(self, dst_path: Optional[str] = None) -> None:
        raise RuntimeError(
            "Tray workfile host does not support saving the current scene."
        )

    def open_workfile(self, filepath: str) -> None:
        pass

    def get_current_workfile(self) -> Optional[str]:
        return None
