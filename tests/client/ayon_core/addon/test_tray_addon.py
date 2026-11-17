"""Tray helpers of 'ITrayAddon'."""
from __future__ import annotations

from unittest import mock

import pytest

from ayon_core.addon import AddonsManager, AYONAddon, ITrayAddon


class _TrayAddon(AYONAddon, ITrayAddon):
    name = "tray_test"
    version = "1.0.0"

    def tray_init(self) -> None:
        pass

    def tray_menu(self, tray_menu) -> None:
        pass

    def tray_start(self) -> None:
        pass

    def tray_exit(self) -> None:
        pass


@pytest.mark.unit
def test_execute_in_main_thread_in_tray():
    """Callback is queued in 'TrayManager' once tray is initialized."""
    tray_manager = mock.Mock(spec=["execute_in_main_thread"])
    addon = _TrayAddon(AddonsManager(initialize=False), {})
    # Same as 'TrayAddonsManager.tray_init'
    addon._tray_manager = tray_manager
    addon.tray_initialized = True

    callback = mock.Mock()
    addon.execute_in_main_thread(callback)

    tray_manager.execute_in_main_thread.assert_called_once_with(callback)
    callback.assert_not_called()
