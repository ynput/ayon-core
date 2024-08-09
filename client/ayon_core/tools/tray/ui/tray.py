import os
import sys
import time
import collections
import atexit
import platform

import ayon_api
from qtpy import QtCore, QtGui, QtWidgets
from aiohttp.web import Response, json_response, Request

from ayon_core import resources, style
from ayon_core.lib import (
    Logger,
    get_ayon_launcher_args,
    run_detached_process,
    is_dev_mode_enabled,
    is_staging_enabled,
    is_running_from_build,
)
from ayon_core.settings import get_studio_settings
from ayon_core.addon import (
    ITrayAction,
    ITrayService,
)
from ayon_core.tools.utils import (
    WrappedCallbackItem,
    get_ayon_qt_app,
)
from ayon_core.tools.tray.lib import (
    set_tray_server_url,
    remove_tray_server_url,
    TrayIsRunningError,
)

from .addons_manager import TrayAddonsManager
from .host_console_listener import HostListener
from .info_widget import InfoWidget
from .dialogs import (
    UpdateDialog,
)


class TrayManager:
    """Cares about context of application.

    Load submenus, actions, separators and addons into tray's context.
    """
    def __init__(self, tray_widget, main_window):
        self.tray_widget = tray_widget
        self.main_window = main_window
        self._info_widget = None
        self._restart_action = None

        self.log = Logger.get_logger(self.__class__.__name__)

        studio_settings = get_studio_settings()

        update_check_interval = studio_settings["core"].get(
            "update_check_interval"
        )
        if update_check_interval is None:
            update_check_interval = 5

        update_check_interval = update_check_interval * 60 * 1000

        # create timer loop to check callback functions
        main_thread_timer = QtCore.QTimer()
        main_thread_timer.setInterval(300)

        update_check_timer = QtCore.QTimer()
        if update_check_interval > 0:
            update_check_timer.setInterval(update_check_interval)

        main_thread_timer.timeout.connect(self._main_thread_execution)
        update_check_timer.timeout.connect(self._on_update_check_timer)

        self._addons_manager = TrayAddonsManager(self)
        self._host_listener = HostListener(self._addons_manager, self)

        self.errors = []

        self._outdated_dialog = None

        self._update_check_timer = update_check_timer
        self._update_check_interval = update_check_interval
        self._main_thread_timer = main_thread_timer
        self._main_thread_callbacks = collections.deque()
        self._execution_in_progress = None
        self._services_submenu = None
        self._start_time = time.time()

        # Cache AYON username used in process
        # - it can change only by changing ayon_api global connection
        #   should be safe for tray application to cache the value only once
        self._cached_username = None
        self._closing = False
        try:
            set_tray_server_url(
                self._addons_manager.webserver_url, False
            )
        except TrayIsRunningError:
            self.log.error("Tray is already running.")
            self._closing = True

    def is_closing(self):
        return self._closing

    @property
    def doubleclick_callback(self):
        """Double-click callback for Tray icon."""
        return self._addons_manager.get_doubleclick_callback()

    def execute_doubleclick(self):
        """Execute double click callback in main thread."""
        callback = self.doubleclick_callback
        if callback:
            self.execute_in_main_thread(callback)

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
        # TODO validate 'self.tray_widget.supportsMessages()'

    def initialize_addons(self):
        """Add addons to tray."""
        if self._closing:
            return

        tray_menu = self.tray_widget.menu
        self._addons_manager.initialize(tray_menu)

        self._addons_manager.add_route(
            "GET", "/tray", self._web_get_tray_info
        )
        self._addons_manager.add_route(
            "POST", "/tray/message", self._web_show_tray_message
        )

        admin_submenu = ITrayAction.admin_submenu(tray_menu)
        tray_menu.addMenu(admin_submenu)

        # Add services if they are
        services_submenu = ITrayService.services_submenu(tray_menu)
        self._services_submenu = services_submenu
        tray_menu.addMenu(services_submenu)

        # Add separator
        tray_menu.addSeparator()

        self._add_version_item()

        # Add Exit action to menu
        exit_action = QtWidgets.QAction("Exit", self.tray_widget)
        exit_action.triggered.connect(self.tray_widget.exit)
        tray_menu.addAction(exit_action)

        # Tell each addon which addons were imported
        # TODO Capture only webserver issues (the only thing that can crash).
        try:
            self._addons_manager.start_addons()
        except Exception:
            self.log.error(
                "Failed to start addons.",
                exc_info=True
            )
            return self.exit()

        # Print time report
        self._addons_manager.print_report()

        self._main_thread_timer.start()

        if self._update_check_interval > 0:
            self._update_check_timer.start()

        self.execute_in_main_thread(self._startup_validations)
        try:
            set_tray_server_url(
                self._addons_manager.webserver_url, True
            )
        except TrayIsRunningError:
            self.log.warning("Other tray started meanwhile. Exiting.")
            self.exit()

    def get_services_submenu(self):
        return self._services_submenu

    def restart(self):
        """Restart Tray tool.

        First creates new process with same argument and close current tray.
        """

        self._closing = True

        args = get_ayon_launcher_args()

        # Create a copy of sys.argv
        additional_args = list(sys.argv)
        # Remove first argument from 'sys.argv'
        # - when running from code the first argument is 'start.py'
        # - when running from build the first argument is executable
        additional_args.pop(0)
        additional_args = [
            arg
            for arg in additional_args
            if arg not in {"--use-staging", "--use-dev"}
        ]

        if is_dev_mode_enabled():
            additional_args.append("--use-dev")
        elif is_staging_enabled():
            additional_args.append("--use-staging")

        args.extend(additional_args)

        envs = dict(os.environ.items())
        for key in {
            "AYON_BUNDLE_NAME",
        }:
            envs.pop(key, None)

        # Remove any existing addon path from 'PYTHONPATH'
        addons_dir = os.environ.get("AYON_ADDONS_DIR", "")
        if addons_dir:
            addons_dir = os.path.normpath(addons_dir)
        addons_dir = addons_dir.lower()

        pythonpath = envs.get("PYTHONPATH") or ""
        new_python_paths = []
        for path in pythonpath.split(os.pathsep):
            if not path:
                continue
            path = os.path.normpath(path)
            if path.lower().startswith(addons_dir):
                continue
            new_python_paths.append(path)

        envs["PYTHONPATH"] = os.pathsep.join(new_python_paths)

        # Start new process
        run_detached_process(args, env=envs)
        # Exit current tray process
        self.exit()

    def exit(self):
        self._closing = True
        if self._main_thread_timer.isActive():
            self.execute_in_main_thread(self.tray_widget.exit)
        else:
            self.tray_widget.exit()

    def on_exit(self):
        remove_tray_server_url()
        self._addons_manager.on_exit()

    def execute_in_main_thread(self, callback, *args, **kwargs):
        if isinstance(callback, WrappedCallbackItem):
            item = callback
        else:
            item = WrappedCallbackItem(callback, *args, **kwargs)

        self._main_thread_callbacks.append(item)

        return item

    async def _web_get_tray_info(self, _request: Request) -> Response:
        if self._cached_username is None:
            self._cached_username = ayon_api.get_user()["name"]

        return json_response({
            "username": self._cached_username,
            "bundle": os.getenv("AYON_BUNDLE_NAME"),
            "dev_mode": is_dev_mode_enabled(),
            "staging_mode": is_staging_enabled(),
            "addons": {
                addon.name: addon.version
                for addon in self._addons_manager.get_enabled_addons()
            },
            "installer_version": os.getenv("AYON_VERSION"),
            "running_time": time.time() - self._start_time,
        })

    async def _web_show_tray_message(self, request: Request) -> Response:
        data = await request.json()
        try:
            title = data["title"]
            message = data["message"]
            icon = data.get("icon")
            msecs = data.get("msecs")
        except KeyError as exc:
            return json_response(
                {
                    "error": f"Missing required data. {exc}",
                    "success": False,
                },
                status=400,
            )

        if icon == "information":
            icon = QtWidgets.QSystemTrayIconInformation
        elif icon == "warning":
            icon = QtWidgets.QSystemTrayIconWarning
        elif icon == "critical":
            icon = QtWidgets.QSystemTrayIcon.Critical
        else:
            icon = None

        self.execute_in_main_thread(
            self.show_tray_message, title, message, icon, msecs
        )
        return json_response({"success": True})

    def _on_update_check_timer(self):
        try:
            bundles = ayon_api.get_bundles()
            user = ayon_api.get_user()
            # This is a workaround for bug in ayon-python-api
            if user.get("code") == 401:
                raise Exception("Unauthorized")
        except Exception:
            self._revalidate_ayon_auth()
            if self._closing:
                return

            try:
                bundles = ayon_api.get_bundles()
            except Exception:
                return

        if is_dev_mode_enabled():
            return

        bundle_type = (
            "stagingBundle"
            if is_staging_enabled()
            else "productionBundle"
        )

        expected_bundle = bundles.get(bundle_type)
        current_bundle = os.environ.get("AYON_BUNDLE_NAME")
        is_expected = expected_bundle == current_bundle
        if is_expected or expected_bundle is None:
            self._restart_action.setVisible(False)
            if (
                self._outdated_dialog is not None
                and self._outdated_dialog.isVisible()
            ):
                self._outdated_dialog.close_silently()
            return

        self._restart_action.setVisible(True)

        if self._outdated_dialog is None:
            self._outdated_dialog = UpdateDialog()
            self._outdated_dialog.restart_requested.connect(
                self._restart_and_install
            )
            self._outdated_dialog.ignore_requested.connect(
                self._outdated_bundle_ignored
            )

        self._outdated_dialog.show()
        self._outdated_dialog.raise_()
        self._outdated_dialog.activateWindow()

    def _revalidate_ayon_auth(self):
        result = self._show_ayon_login(restart_on_token_change=False)
        if self._closing:
            return False

        if not result.new_token:
            self.exit()
            return False
        return True

    def _restart_and_install(self):
        self.restart()

    def _outdated_bundle_ignored(self):
        self.show_tray_message(
            "AYON update ignored",
            (
                "Please restart AYON launcher as soon as possible"
                " to propagate updates."
            )
        )

    def _main_thread_execution(self):
        try:
            if self._execution_in_progress:
                return
            self._execution_in_progress = True
            for _ in range(len(self._main_thread_callbacks)):
                if self._main_thread_callbacks:
                    item = self._main_thread_callbacks.popleft()
                    try:
                        item.execute()
                    except BaseException:
                        self.log.erorr(
                            "Main thread execution failed", exc_info=True
                        )

            self._execution_in_progress = False

        except KeyboardInterrupt:
            self.execute_in_main_thread(self.exit)

    def _startup_validations(self):
        """Run possible startup validations."""
        # Trigger bundle validation on start
        self._update_check_timer.timeout.emit()

    def _add_version_item(self):
        tray_menu = self.tray_widget.menu
        login_action = QtWidgets.QAction("Login", self.tray_widget)
        login_action.triggered.connect(self._on_ayon_login)
        tray_menu.addAction(login_action)
        version_string = os.getenv("AYON_VERSION", "AYON Info")

        version_action = QtWidgets.QAction(version_string, self.tray_widget)
        version_action.triggered.connect(self._on_version_action)

        restart_action = QtWidgets.QAction(
            "Restart && Update", self.tray_widget
        )
        restart_action.triggered.connect(self._on_restart_action)
        restart_action.setVisible(False)

        tray_menu.addAction(version_action)
        tray_menu.addAction(restart_action)
        tray_menu.addSeparator()

        self._restart_action = restart_action

    def _on_ayon_login(self):
        self.execute_in_main_thread(
            self._show_ayon_login,
            restart_on_token_change=True
        )

    def _show_ayon_login(self, restart_on_token_change):
        from ayon_common.connection.credentials import change_user_ui

        result = change_user_ui()
        if result.shutdown:
            self.exit()
            return result

        restart = result.restart
        if restart_on_token_change and result.token_changed:
            restart = True

        if restart:
            # Remove environment variables from current connection
            # - keep develop, staging, headless values
            for key in {
                "AYON_SERVER_URL",
                "AYON_API_KEY",
                "AYON_BUNDLE_NAME",
            }:
                os.environ.pop(key, None)
            self.restart()
        return result

    def _on_restart_action(self):
        self.restart()

    def _restart_ayon(self):
        args = get_ayon_launcher_args()

        # Create a copy of sys.argv
        additional_args = list(sys.argv)
        # Remove first argument from 'sys.argv'
        # - when running from code the first argument is 'start.py'
        # - when running from build the first argument is executable
        additional_args.pop(0)
        additional_args = [
            arg
            for arg in additional_args
            if arg not in {"--use-staging", "--use-dev"}
        ]

        if is_dev_mode_enabled():
            additional_args.append("--use-dev")
        elif is_staging_enabled():
            additional_args.append("--use-staging")

        args.extend(additional_args)

        envs = dict(os.environ.items())
        for key in {
            "AYON_BUNDLE_NAME",
        }:
            envs.pop(key, None)

        run_detached_process(args, env=envs)
        self.exit()

    def _on_version_action(self):
        if self._info_widget is None:
            self._info_widget = InfoWidget()

        self._info_widget.show()
        self._info_widget.raise_()
        self._info_widget.activateWindow()


class SystemTrayIcon(QtWidgets.QSystemTrayIcon):
    """Tray widget.

    :param parent: Main widget that cares about all GUIs
    :type parent: QtWidgets.QMainWindow
    """

    doubleclick_time_ms = 100

    def __init__(self, parent):
        icon = QtGui.QIcon(resources.get_ayon_icon_filepath())

        super().__init__(icon, parent)

        self._exited = False

        self._doubleclick = False
        self._click_pos = None
        self._initializing_addons = False

        # Store parent - QtWidgets.QMainWindow()
        self._parent = parent

        # Setup menu in Tray
        self.menu = QtWidgets.QMenu()
        self.menu.setStyleSheet(style.load_stylesheet())

        # Set addons
        self._tray_manager = TrayManager(self, parent)

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

    def is_closing(self) -> bool:
        return self._tray_manager.is_closing()

    @property
    def initializing_addons(self):
        return self._initializing_addons

    def initialize_addons(self):
        self._initializing_addons = True
        try:
            self._tray_manager.initialize_addons()
        finally:
            self._initializing_addons = False

    def _click_timer_timeout(self):
        self._click_timer.stop()
        doubleclick = self._doubleclick
        # Reset bool value
        self._doubleclick = False
        if doubleclick:
            self._tray_manager.execute_doubleclick()
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
            if self._tray_manager.doubleclick_callback:
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
        self._tray_manager.on_exit()
        QtCore.QCoreApplication.exit()


class TrayStarter(QtCore.QObject):
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
        if self._tray_widget.is_closing():
            self._start_timer.stop()
            self._tray_widget.exit()
            return

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
    app = get_ayon_qt_app()

    starter = TrayStarter(app)  # noqa F841

    if not is_running_from_build() and os.name == "nt":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            u"ayon_tray"
        )

    sys.exit(app.exec_())
