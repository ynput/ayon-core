import collections
import os
import sys
import atexit

import platform

from qtpy import QtCore, QtGui, QtWidgets

from ayon_core import resources, style
from ayon_core.lib import (
    Logger,
    get_ayon_launcher_args,
    run_detached_process,
)
from ayon_core.lib import is_running_from_build
from ayon_core.addon import (
    ITrayAction,
    ITrayService,
    TrayAddonsManager,
)
from ayon_core.settings import get_system_settings
from ayon_core.tools.utils import (
    WrappedCallbackItem,
    get_openpype_qt_app,
)

from .pype_info_widget import PypeInfoWidget


# TODO PixmapLabel should be moved to 'utils' in other future PR so should be
#   imported from there
class PixmapLabel(QtWidgets.QLabel):
    """Label resizing image to height of font."""
    def __init__(self, pixmap, parent):
        super(PixmapLabel, self).__init__(parent)
        self._empty_pixmap = QtGui.QPixmap(0, 0)
        self._source_pixmap = pixmap

    def set_source_pixmap(self, pixmap):
        """Change source image."""
        self._source_pixmap = pixmap
        self._set_resized_pix()

    def _get_pix_size(self):
        size = self.fontMetrics().height() * 3
        return size, size

    def _set_resized_pix(self):
        if self._source_pixmap is None:
            self.setPixmap(self._empty_pixmap)
            return
        width, height = self._get_pix_size()
        self.setPixmap(
            self._source_pixmap.scaled(
                width,
                height,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation
            )
        )

    def resizeEvent(self, event):
        self._set_resized_pix()
        super(PixmapLabel, self).resizeEvent(event)


class TrayManager:
    """Cares about context of application.

    Load submenus, actions, separators and addons into tray's context.
    """
    def __init__(self, tray_widget, main_window):
        self.tray_widget = tray_widget
        self.main_window = main_window
        self.pype_info_widget = None
        self._restart_action = None

        self.log = Logger.get_logger(self.__class__.__name__)

        system_settings = get_system_settings()

        version_check_interval = system_settings["general"].get(
            "version_check_interval"
        )
        if version_check_interval is None:
            version_check_interval = 5
        self._version_check_interval = version_check_interval * 60 * 1000

        self._addons_manager = TrayAddonsManager()

        self.errors = []

        self.main_thread_timer = None
        self._main_thread_callbacks = collections.deque()
        self._execution_in_progress = None

    @property
    def doubleclick_callback(self):
        """Double-click callback for Tray icon."""
        callback_name = self._addons_manager.doubleclick_callback
        return self._addons_manager.doubleclick_callbacks.get(callback_name)

    def execute_doubleclick(self):
        """Execute double click callback in main thread."""
        callback = self.doubleclick_callback
        if callback:
            self.execute_in_main_thread(callback)

    def _restart_and_install(self):
        self.restart(use_expected_version=True)

    def execute_in_main_thread(self, callback, *args, **kwargs):
        if isinstance(callback, WrappedCallbackItem):
            item = callback
        else:
            item = WrappedCallbackItem(callback, *args, **kwargs)

        self._main_thread_callbacks.append(item)

        return item

    def _main_thread_execution(self):
        if self._execution_in_progress:
            return
        self._execution_in_progress = True
        for _ in range(len(self._main_thread_callbacks)):
            if self._main_thread_callbacks:
                item = self._main_thread_callbacks.popleft()
                item.execute()

        self._execution_in_progress = False

    def initialize_addons(self):
        """Add addons to tray."""

        self._addons_manager.initialize(self, self.tray_widget.menu)

        admin_submenu = ITrayAction.admin_submenu(self.tray_widget.menu)
        self.tray_widget.menu.addMenu(admin_submenu)

        # Add services if they are
        services_submenu = ITrayService.services_submenu(self.tray_widget.menu)
        self.tray_widget.menu.addMenu(services_submenu)

        # Add separator
        self.tray_widget.menu.addSeparator()

        self._add_version_item()

        # Add Exit action to menu
        exit_action = QtWidgets.QAction("Exit", self.tray_widget)
        exit_action.triggered.connect(self.tray_widget.exit)
        self.tray_widget.menu.addAction(exit_action)

        # Tell each addon which addons were imported
        self._addons_manager.start_addons()

        # Print time report
        self._addons_manager.print_report()

        # create timer loop to check callback functions
        main_thread_timer = QtCore.QTimer()
        main_thread_timer.setInterval(300)
        main_thread_timer.timeout.connect(self._main_thread_execution)
        main_thread_timer.start()

        self.main_thread_timer = main_thread_timer

        self.execute_in_main_thread(self._startup_validations)

    def _startup_validations(self):
        """Run possible startup validations."""
        pass

    def show_tray_message(self, title, message, icon=None, msecs=None):
        """Show tray message.

        Args:
            title (str): Title of message.
            message (str): Content of message.
            icon (QSystemTrayIcon.MessageIcon): Message's icon. Default is
                Information icon, may differ by Qt version.
            msecs (int): Duration of message visibility in milliseconds.
                Default is 10000 msecs, may differ by Qt version.
        """
        args = [title, message]
        kwargs = {}
        if icon:
            kwargs["icon"] = icon
        if msecs:
            kwargs["msecs"] = msecs

        self.tray_widget.showMessage(*args, **kwargs)

    def _add_version_item(self):
        login_action = QtWidgets.QAction("Login", self.tray_widget)
        login_action.triggered.connect(self._on_ayon_login)
        self.tray_widget.menu.addAction(login_action)

        version_string = os.getenv("AYON_VERSION", "AYON Info")

        version_action = QtWidgets.QAction(version_string, self.tray_widget)
        version_action.triggered.connect(self._on_version_action)

        restart_action = QtWidgets.QAction(
            "Restart && Update", self.tray_widget
        )
        restart_action.triggered.connect(self._on_restart_action)
        restart_action.setVisible(False)

        self.tray_widget.menu.addAction(version_action)
        self.tray_widget.menu.addAction(restart_action)
        self.tray_widget.menu.addSeparator()

        self._restart_action = restart_action

    def _on_ayon_login(self):
        self.execute_in_main_thread(self._show_ayon_login)

    def _show_ayon_login(self):
        from ayon_common.connection.credentials import change_user_ui

        result = change_user_ui()
        if result.shutdown:
            self.exit()

        elif result.restart or result.token_changed:
            # Remove environment variables from current connection
            # - keep develop, staging, headless values
            for key in {
                "AYON_SERVER_URL",
                "AYON_API_KEY",
                "AYON_BUNDLE_NAME",
            }:
                os.environ.pop(key, None)
            self.restart()

    def _on_restart_action(self):
        self.restart(use_expected_version=True)

    def restart(self, use_expected_version=False, reset_version=False):
        """Restart Tray tool.

        First creates new process with same argument and close current tray.

        Args:
            use_expected_version(bool): OpenPype version is set to expected
                version.
            reset_version(bool): OpenPype version is cleaned up so igniters
                logic will decide which version will be used.
        """
        args = get_ayon_launcher_args()
        envs = dict(os.environ.items())

        # Create a copy of sys.argv
        additional_args = list(sys.argv)
        # Remove first argument from 'sys.argv'
        # - when running from code the first argument is 'start.py'
        # - when running from build the first argument is executable
        additional_args.pop(0)

        cleanup_additional_args = False
        if use_expected_version:
            cleanup_additional_args = True
            reset_version = True

        # Pop OPENPYPE_VERSION
        if reset_version:
            cleanup_additional_args = True
            envs.pop("OPENPYPE_VERSION", None)

        if cleanup_additional_args:
            _additional_args = []
            for arg in additional_args:
                if arg == "--use-staging" or arg.startswith("--use-version"):
                    continue
                _additional_args.append(arg)
            additional_args = _additional_args

        args.extend(additional_args)
        run_detached_process(args, env=envs)
        self.exit()

    def exit(self):
        self.tray_widget.exit()

    def on_exit(self):
        self._addons_manager.on_exit()

    def _on_version_action(self):
        if self.pype_info_widget is None:
            self.pype_info_widget = PypeInfoWidget()

        self.pype_info_widget.show()
        self.pype_info_widget.raise_()
        self.pype_info_widget.activateWindow()


class SystemTrayIcon(QtWidgets.QSystemTrayIcon):
    """Tray widget.

    :param parent: Main widget that cares about all GUIs
    :type parent: QtWidgets.QMainWindow
    """

    doubleclick_time_ms = 100

    def __init__(self, parent):
        icon = QtGui.QIcon(resources.get_ayon_icon_filepath())

        super(SystemTrayIcon, self).__init__(icon, parent)

        self._exited = False

        # Store parent - QtWidgets.QMainWindow()
        self.parent = parent

        # Setup menu in Tray
        self.menu = QtWidgets.QMenu()
        self.menu.setStyleSheet(style.load_stylesheet())

        # Set addons
        self.tray_man = TrayManager(self, self.parent)

        # Add menu to Context of SystemTrayIcon
        self.setContextMenu(self.menu)

        atexit.register(self.exit)

        # Catch activate event for left click if not on MacOS
        #   - MacOS has this ability by design and is harder to modify this
        #       behavior
        if platform.system().lower() == "darwin":
            return

        self.activated.connect(self.on_systray_activated)

        click_timer = QtCore.QTimer()
        click_timer.setInterval(self.doubleclick_time_ms)
        click_timer.timeout.connect(self._click_timer_timeout)

        self._click_timer = click_timer
        self._doubleclick = False
        self._click_pos = None

        self._initializing_addons = False

    @property
    def initializing_addons(self):
        return self._initializing_addons

    def initialize_addons(self):
        self._initializing_addons = True
        self.tray_man.initialize_addons()
        self._initializing_addons = False

    def _click_timer_timeout(self):
        self._click_timer.stop()
        doubleclick = self._doubleclick
        # Reset bool value
        self._doubleclick = False
        if doubleclick:
            self.tray_man.execute_doubleclick()
        else:
            self._show_context_menu()

    def _show_context_menu(self):
        pos = self._click_pos
        self._click_pos = None
        if pos is None:
            pos = QtGui.QCursor().pos()
        self.contextMenu().popup(pos)

    def on_systray_activated(self, reason):
        # show contextMenu if left click
        if reason == QtWidgets.QSystemTrayIcon.Trigger:
            if self.tray_man.doubleclick_callback:
                self._click_pos = QtGui.QCursor().pos()
                self._click_timer.start()
            else:
                self._show_context_menu()

        elif reason == QtWidgets.QSystemTrayIcon.DoubleClick:
            self._doubleclick = True

    def exit(self):
        """ Exit whole application.

        - Icon won't stay in tray after exit.
        """
        if self._exited:
            return
        self._exited = True

        self.hide()
        self.tray_man.on_exit()
        QtCore.QCoreApplication.exit()


class PypeTrayStarter(QtCore.QObject):
    def __init__(self, app):
        app.setQuitOnLastWindowClosed(False)
        self._app = app
        self._splash = None

        main_window = QtWidgets.QMainWindow()
        tray_widget = SystemTrayIcon(main_window)

        start_timer = QtCore.QTimer()
        start_timer.setInterval(100)
        start_timer.start()

        start_timer.timeout.connect(self._on_start_timer)

        self._main_window = main_window
        self._tray_widget = tray_widget
        self._timer_counter = 0
        self._start_timer = start_timer

    def _on_start_timer(self):
        if self._timer_counter == 0:
            self._timer_counter += 1
            splash = self._get_splash()
            splash.show()
            self._tray_widget.show()
            # Make sure tray and splash are painted out
            QtWidgets.QApplication.processEvents()

        elif self._timer_counter == 1:
            # Second processing of events to make sure splash is painted
            QtWidgets.QApplication.processEvents()
            self._timer_counter += 1
            self._tray_widget.initialize_addons()

        elif not self._tray_widget.initializing_addons:
            splash = self._get_splash()
            splash.hide()
            self._start_timer.stop()

    def _get_splash(self):
        if self._splash is None:
            self._splash = self._create_splash()
        return self._splash

    def _create_splash(self):
        splash_pix = QtGui.QPixmap(resources.get_ayon_splash_filepath())
        splash = QtWidgets.QSplashScreen(splash_pix)
        splash.setMask(splash_pix.mask())
        splash.setEnabled(False)
        splash.setWindowFlags(
            QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.FramelessWindowHint
        )
        return splash


def main():
    app = get_openpype_qt_app()

    starter = PypeTrayStarter(app)

    # TODO remove when pype.exe will have an icon
    if not is_running_from_build() and os.name == "nt":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            u"ayon_tray"
        )

    sys.exit(app.exec_())
