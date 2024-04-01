import os

from ayon_core import AYON_CORE_ROOT
from ayon_core.addon import AYONAddon, ITrayAction


class LauncherAction(AYONAddon, ITrayAction):
    label = "Launcher"
    name = "launcher_tool"

    def initialize(self, settings):

        # Tray attributes
        self._window = None

    def tray_init(self):
        self._create_window()

        self.add_doubleclick_callback(self._show_launcher)

    def tray_start(self):
        return

    def connect_with_addons(self, enabled_modules):
        # Register actions
        if not self.tray_initialized:
            return

        from ayon_core.pipeline.actions import register_launcher_action_path

        actions_dir = os.path.join(AYON_CORE_ROOT, "plugins", "actions")
        if os.path.exists(actions_dir):
            register_launcher_action_path(actions_dir)

        actions_paths = self.manager.collect_plugin_paths()["actions"]
        for path in actions_paths:
            if path and os.path.exists(path):
                register_launcher_action_path(path)

    def on_action_trigger(self):
        """Implementation for ITrayAction interface.

        Show launcher tool on action trigger.
        """

        self._show_launcher()

    def _create_window(self):
        if self._window:
            return
        from ayon_core.tools.launcher.ui import LauncherWindow
        self._window = LauncherWindow()

    def _show_launcher(self):
        if self._window is None:
            return
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()
