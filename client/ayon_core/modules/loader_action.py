from ayon_core.addon import AYONAddon, ITrayAddon


class LoaderAddon(AYONAddon, ITrayAddon):
    name = "loader_tool"
    version = "1.0.0"

    def initialize(self, settings):
        # Tray attributes
        self._loader_imported = None
        self._loader_window = None

    def tray_init(self):
        # Add library tool
        self._loader_imported = False
        try:
            from ayon_core.tools.loader.ui import LoaderWindow  # noqa F401

            self._loader_imported = True
        except Exception:
            self.log.warning(
                "Couldn't load Loader tool for tray.",
                exc_info=True
            )

    # Definition of Tray menu
    def tray_menu(self, tray_menu):
        if not self._loader_imported:
            return

        from qtpy import QtWidgets
        # Actions
        action_loader = QtWidgets.QAction(
            "Loader", tray_menu
        )

        action_loader.triggered.connect(self.show_loader)

        tray_menu.addAction(action_loader)

    def tray_start(self, *_a, **_kw):
        return

    def tray_exit(self, *_a, **_kw):
        return

    def show_loader(self):
        if self._loader_window is None:
            from ayon_core.pipeline import install_ayon_plugins

            self._init_loader()

            install_ayon_plugins()

        self._loader_window.show()

        # Raise and activate the window
        # for MacOS
        self._loader_window.raise_()
        # for Windows
        self._loader_window.activateWindow()

    def _init_loader(self):
        from ayon_core.tools.loader.ui import LoaderWindow

        libraryloader = LoaderWindow()

        self._loader_window = libraryloader
