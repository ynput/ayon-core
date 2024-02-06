from ayon_core.modules import AYONAddon, ITrayModule


class LibraryLoaderAddon(AYONAddon, ITrayModule):
    name = "library_tool"

    def initialize(self, modules_settings):
        # Tray attributes
        self._library_loader_imported = None
        self._library_loader_window = None

    def tray_init(self):
        # Add library tool
        self._library_loader_imported = False
        try:
            from ayon_core.tools.libraryloader import LibraryLoaderWindow

            self._library_loader_imported = True
        except Exception:
            self.log.warning(
                "Couldn't load Library loader tool for tray.",
                exc_info=True
            )

    # Definition of Tray menu
    def tray_menu(self, tray_menu):
        if not self._library_loader_imported:
            return

        from qtpy import QtWidgets
        # Actions
        action_library_loader = QtWidgets.QAction(
            "Loader", tray_menu
        )

        action_library_loader.triggered.connect(self.show_library_loader)

        tray_menu.addAction(action_library_loader)

    def tray_start(self, *_a, **_kw):
        return

    def tray_exit(self, *_a, **_kw):
        return

    def show_library_loader(self):
        if self._library_loader_window is None:
            from ayon_core.pipeline import install_openpype_plugins

            self._init_library_loader()

            install_openpype_plugins()

        self._library_loader_window.show()

        # Raise and activate the window
        # for MacOS
        self._library_loader_window.raise_()
        # for Windows
        self._library_loader_window.activateWindow()

    def _init_library_loader(self):
        from ayon_core.tools.loader.ui import LoaderWindow

        libraryloader = LoaderWindow()

        self._library_loader_window = libraryloader
