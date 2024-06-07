from ayon_core.addon import AYONAddon, ITrayAction


class PythonInterpreterAction(AYONAddon, ITrayAction):
    label = "Console"
    name = "python_interpreter"
    version = "1.0.0"
    admin_action = True

    def initialize(self, settings):
        self._interpreter_window = None

    def tray_init(self):
        self.create_interpreter_window()

    def tray_exit(self):
        if self._interpreter_window is not None:
            self._interpreter_window.save_registry()

    def create_interpreter_window(self):
        """Initializa Settings Qt window."""
        if self._interpreter_window:
            return

        from ayon_core.modules.python_console_interpreter.window import (
            PythonInterpreterWidget
        )

        self._interpreter_window = PythonInterpreterWidget()

    def on_action_trigger(self):
        self.show_interpreter_window()

    def show_interpreter_window(self):
        self.create_interpreter_window()

        if self._interpreter_window.isVisible():
            self._interpreter_window.activateWindow()
            self._interpreter_window.raise_()
            return

        self._interpreter_window.show()
