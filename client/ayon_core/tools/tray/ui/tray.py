import os
import sys
import math
import time
import collections
import atexit
from packaging.version import parse
import platform

import ayon_api
from qtpy import QtCore, QtGui, QtWidgets, QT_VERSION
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
from ayon_core.lib.events import QueuedEventSystem
from ayon_core.settings import get_studio_settings
from ayon_core.addon import (
    ITrayAddon,
    ITrayService,
)
from ayon_core.pipeline import install_ayon_plugins
from ayon_core.tools.utils import (
    WrappedCallbackItem,
    get_ayon_qt_app,
)
from ayon_core.tools.common_models import WSEventsModel
from ayon_core.tools.tray.lib import (
    set_tray_server_url,
    remove_tray_server_url,
    TrayIsRunningError,
)
from ayon_core.tools.launcher.ui import LauncherWindow
from ayon_core.tools.console_interpreter.ui import ConsoleInterpreterWindow
from ayon_core.tools.publisher.publish_report_viewer import (
    PublishReportViewerWindow,
)

from .addons_manager import TrayAddonsManager
from .host_console_listener import HostListener
from .info_widget import InfoWidget
from .dialogs import UpdateDialog
from ._macos_fix import install_clickcount_fix


class TrayManager:
    """Cares about context of application.

    Load submenus, actions, separators and addons into tray's context.
    """
    # Delay of notification about lost connection to server (in ms)
    connection_lost_notification_delay = 60 * 1000

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

        # Server events (connection state, bundle changes) received
        #   via websocket, processed in '_main_thread_execution'
        self._event_system = QueuedEventSystem()
        self._ws_events_model = WSEventsModel(self)
        # Connection was lost (icon shows orange dot)
        self._connection_lost = False
        # User was notified about lost connection with tray message
        self._connection_lost_notified = False
        # Show notification only if connection is not restored in time,
        #   short outages (e.g. server restart) only change the icon
        connection_lost_timer = QtCore.QTimer()
        connection_lost_timer.setSingleShot(True)
        connection_lost_timer.setInterval(
            self.connection_lost_notification_delay
        )
        connection_lost_timer.timeout.connect(
            self._on_connection_lost_timer
        )
        self._connection_lost_timer = connection_lost_timer
        # Single bundle change can trigger multiple events in short time
        bundle_validation_timer = QtCore.QTimer()
        bundle_validation_timer.setSingleShot(True)
        bundle_validation_timer.setInterval(1000)
        bundle_validation_timer.timeout.connect(self._validate_bundle)
        self._bundle_validation_timer = bundle_validation_timer

        self._addons_manager = TrayAddonsManager(self)
        self._host_listener = HostListener(self._addons_manager, self)

        self.errors = []

        self._outdated_dialog = None

        self._launcher_window = None
        self._browser_window = None
        self._console_window = ConsoleInterpreterWindow()
        self._publish_report_viewer_window = PublishReportViewerWindow()

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

    def emit_event(self, topic, data=None, source=None):
        """Emit event, used by 'WSEventsModel' for connection events."""
        if data is None:
            data = {}
        self._event_system.emit(topic, data, source)

    def register_event_callback(self, topic, callback):
        self._event_system.add_callback(topic, callback)

    @property
    def doubleclick_callback(self):
        """Double-click callback for Tray icon."""
        callback = self._addons_manager.get_doubleclick_callback()
        if callback is None:
            callback = self._show_launcher_window
        return callback

    def execute_doubleclick(self):
        """Execute double click callback in main thread."""
        callback = self.doubleclick_callback
        if callback is not None:
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
        # Add launcher at first place
        launcher_action = QtWidgets.QAction(
            "Launcher", tray_menu
        )
        launcher_action.triggered.connect(self._show_launcher_window)
        tray_menu.addAction(launcher_action)

        console_action = ITrayAddon.add_action_to_admin_submenu(
            "Console", tray_menu
        )
        console_action.triggered.connect(self._show_console_window)

        publish_report_viewer_action = ITrayAddon.add_action_to_admin_submenu(
            "Publish report viewer", tray_menu
        )
        publish_report_viewer_action.triggered.connect(
            self._show_publish_report_viewer
        )

        self._addons_manager.initialize(tray_menu)

        # Add browser action after addon actions
        browser_action = QtWidgets.QAction(
            "Browser", tray_menu
        )
        browser_action.triggered.connect(self._show_browser_window)
        tray_menu.addAction(browser_action)

        self._addons_manager.add_route(
            "GET", "/tray", self._web_get_tray_info
        )
        self._addons_manager.add_route(
            "POST", "/tray/message", self._web_show_tray_message
        )

        admin_submenu = ITrayAddon.admin_submenu(tray_menu)
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

        self._init_server_events()
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

        project_bundle = os.getenv("AYON_BUNDLE_NAME")
        studio_bundle = os.getenv("AYON_STUDIO_BUNDLE_NAME")
        if studio_bundle and project_bundle != studio_bundle:
            self.log.info(
                f"Project bundle '{project_bundle}' is defined, but tray"
                " cannot be running in project scope. Restarting tray to use"
                " studio bundle."
            )
            self.restart()

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

        if "--project" in additional_args:
            idx = additional_args.index("--project")
            additional_args.pop(idx)
            additional_args.pop(idx)

        args.extend(additional_args)

        envs = dict(os.environ.items())
        for key in {
            "AYON_BUNDLE_NAME",
            "AYON_STUDIO_BUNDLE_NAME",
            "AYON_PROJECT_NAME",
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
            "studio_bundle": os.getenv("AYON_STUDIO_BUNDLE_NAME"),
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
            icon = QtWidgets.QSystemTrayIcon.Information
        elif icon == "warning":
            icon = QtWidgets.QSystemTrayIcon.Warning
        elif icon == "critical":
            icon = QtWidgets.QSystemTrayIcon.Critical
        else:
            icon = None

        self.execute_in_main_thread(
            self.show_tray_message, title, message, icon, msecs
        )
        return json_response({"success": True})

    def _init_server_events(self):
        """Listen to AYON server events.

        Connection state and authentication are watched by event hub, so
            the tray does not have to poll the server. Bundle events
            trigger validation of the bundle used by the tray.
        """
        self.register_event_callback(
            "ayon.connection.opened", self._on_server_connection_opened
        )
        self.register_event_callback(
            "ayon.connection.closed", self._on_server_connection_closed
        )
        self.register_event_callback(
            "ayon.auth.failed", self._on_server_auth_failed
        )
        # - 'bundle.created', 'bundle.updated', 'bundle.status_changed'
        self._ws_events_model.register_ayon_event_callback(
            "bundle.*", self._on_bundle_event
        )
        self._ws_events_model.process_events()

    def _on_server_connection_opened(self):
        if not self._connection_lost:
            return
        self._connection_lost = False
        self._connection_lost_timer.stop()
        self.tray_widget.set_connection_status(
            SystemTrayIcon.CONNECTION_OK
        )
        # Tell user about restored connection only if was told it was lost
        if self._connection_lost_notified:
            self._connection_lost_notified = False
            self.show_tray_message(
                "AYON server connection restored",
                "Connection to AYON server was restored.",
            )
        # Bundles might have changed while the server was not available
        self._bundle_validation_timer.start()

    def _on_server_connection_closed(self):
        if self._connection_lost:
            return
        self._connection_lost = True
        self.tray_widget.set_connection_status(
            SystemTrayIcon.CONNECTION_LOST
        )
        self._connection_lost_timer.start()

    def _on_connection_lost_timer(self):
        if not self._connection_lost or self._closing:
            return
        self.tray_widget.set_connection_status(
            SystemTrayIcon.CONNECTION_LOST_LONG
        )
        self._connection_lost_notified = True
        self.show_tray_message(
            "AYON server connection lost",
            "Connection to AYON server was lost. Waiting for reconnection.",
            QtWidgets.QSystemTrayIcon.Warning,
        )

    def _on_server_auth_failed(self):
        self._revalidate_ayon_auth()

    def _on_bundle_event(self, event):
        self.log.debug(
            f"Bundle event '{event.topic}' received, validating bundle."
        )
        self._bundle_validation_timer.start()

    def _on_update_check_timer(self):
        self._validate_bundle()

    def _validate_bundle(self):
        """Check if bundle used by tray is still production/staging bundle.

        Connection and authentication issues are handled by server events,
            so the validation is skipped when server is not available.
        """
        if self._closing or is_dev_mode_enabled():
            return

        if self._ws_events_model.get_connection_state() is False:
            return

        try:
            bundles = ayon_api.get_bundles()
        except Exception:
            self.log.debug("Failed to get bundles.", exc_info=True)
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
            try:
                self._ws_events_model.process_events()
            except Exception:
                self.log.error(
                    "Failed to process server events", exc_info=True
                )
            for _ in range(len(self._main_thread_callbacks)):
                if self._main_thread_callbacks:
                    item = self._main_thread_callbacks.popleft()
                    try:
                        item.execute()
                    except BaseException:
                        self.log.error(
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
                "AYON_STUDIO_BUNDLE_NAME",
                "AYON_PROJECT_NAME",
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
            "AYON_STUDIO_BUNDLE_NAME",
            "AYON_PROJECT_NAME",
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

    def _show_launcher_window(self):
        if self._launcher_window is None:
            self._launcher_window = LauncherWindow()

        self._launcher_window.show()
        self._launcher_window.raise_()
        self._launcher_window.activateWindow()

    def _show_browser_window(self):
        if self._browser_window is None:
            from ayon_core.tools.utils.host_tools import use_legacy_loader

            if use_legacy_loader():
                from ayon_core.tools.loader.ui import LoaderWindow

                window_class = LoaderWindow
            else:
                from ayon_core.tools.browser.ui import BrowserWindow

                window_class = BrowserWindow
            self._browser_window = window_class()
            self._browser_window.setWindowTitle("AYON Browser")
            install_ayon_plugins()

        self._browser_window.show()
        self._browser_window.raise_()
        self._browser_window.activateWindow()

    def _show_console_window(self):
        self._console_window.show()
        self._console_window.raise_()
        self._console_window.activateWindow()

    def _show_publish_report_viewer(self):
        self._publish_report_viewer_window.refresh()
        self._publish_report_viewer_window.show()
        self._publish_report_viewer_window.raise_()
        self._publish_report_viewer_window.activateWindow()


class SystemTrayIcon(QtWidgets.QSystemTrayIcon):
    """Tray widget.

    Mouse behavior (Windows and Linux):
        - Left click: show tray menu (delayed by system double-click
            interval so it can be distinguished from double-click).
        - Double click: execute double-click callback (e.g. launcher).
        - Right click: show tray menu (handled by Qt).

    Menu opened by a click ignores mouse clicks for a short time after
        it is shown. Without that the second click of a (slow) double-click
        lands on the menu item under the cursor, which is usually 'Exit'.

    :param parent: Main widget that cares about all GUIs
    :type parent: QtWidgets.QMainWindow
    """

    # Fallback values (in ms) if the system value is not available
    default_doubleclick_time_ms = 400
    # How long after the menu is shown mouse clicks are ignored
    menu_click_guard_ms = 400

    # Connection status shown in icon
    # - connected: no dot
    # - lost: orange dot fading in/out (connection may be restored soon)
    # - lost long: solid red dot
    CONNECTION_OK = "ok"
    CONNECTION_LOST = "lost"
    CONNECTION_LOST_LONG = "lost_long"
    # Duration of one fade in/out cycle
    blink_cycle_ms = 800
    # Number of icon frames per cycle (icon is updated for each frame)
    blink_frames = 20

    def __init__(self, parent):
        icon = QtGui.QIcon(resources.get_ayon_icon_filepath())

        super().__init__(icon, parent)

        self._icon = icon
        self._dot_icons = {}
        self._connection_status = self.CONNECTION_OK
        self._blink_frame = 0

        blink_timer = QtCore.QTimer()
        blink_timer.setInterval(
            max(1, self.blink_cycle_ms // self.blink_frames)
        )
        blink_timer.timeout.connect(self._on_blink_timer)
        self._blink_timer = blink_timer
        self._exited = False

        self._click_pos = None
        self._initializing_addons = False
        # Timestamps used to filter out unwanted clicks
        self._menu_shown_at = 0.0
        self._menu_hidden_at = 0.0
        self._ignore_trigger_until = 0.0

        doubleclick_time_ms = QtWidgets.QApplication.doubleClickInterval()
        if not doubleclick_time_ms or doubleclick_time_ms <= 0:
            doubleclick_time_ms = self.default_doubleclick_time_ms
        self._doubleclick_time_ms = doubleclick_time_ms

        # Store parent - QtWidgets.QMainWindow()
        self._parent = parent

        # Setup menu in Tray
        self.menu = QtWidgets.QMenu()
        self.menu.setStyleSheet(style.load_stylesheet())
        self.menu.aboutToShow.connect(self._on_menu_about_to_show)
        self.menu.aboutToHide.connect(self._on_menu_about_to_hide)
        self.menu.installEventFilter(self)

        # Set addons
        self._tray_manager = TrayManager(self, parent)

        # Add menu to Context of SystemTrayIcon
        #   - right click (Context) is handled by Qt itself
        self.setContextMenu(self.menu)

        atexit.register(self.exit)

        self._click_timer = None

        # Catch activate event for left click if not on MacOS
        #   - MacOS has this ability by design and is harder to modify this
        #       behavior
        if platform.system().lower() == "darwin":
            return

        self.activated.connect(self.on_systray_activated)

        click_timer = QtCore.QTimer(self)
        click_timer.setSingleShot(True)
        click_timer.setInterval(self._doubleclick_time_ms)
        click_timer.timeout.connect(self._click_timer_timeout)

        self._click_timer = click_timer

    def is_closing(self) -> bool:
        return self._tray_manager.is_closing()

    def set_connection_status(self, status: str) -> None:
        """Show connection status to server in icon.

        Args:
            status (str): One of 'CONNECTION_OK', 'CONNECTION_LOST' or
                'CONNECTION_LOST_LONG'.

        """
        if self._connection_status == status:
            return
        self._connection_status = status
        self._blink_timer.stop()
        if status == self.CONNECTION_OK:
            self.setIcon(self._icon)
            self.setToolTip("")
            return

        self.setToolTip("AYON - Connection to server lost")
        if status == self.CONNECTION_LOST:
            self._blink_frame = 0
            self.setIcon(self._get_dot_icon("#ff8c00"))
            self._blink_timer.start()
        else:
            self.setIcon(self._get_dot_icon("#e53935"))

    def _on_blink_timer(self):
        if self._connection_status != self.CONNECTION_LOST:
            self._blink_timer.stop()
            return
        self._blink_frame = (self._blink_frame + 1) % self.blink_frames
        # Cosine curve - starts fully visible, fades out and in again
        progress = self._blink_frame / self.blink_frames
        opacity = (math.cos(progress * 2 * math.pi) + 1) * 0.5
        self.setIcon(self._get_dot_icon("#ff8c00", opacity))

    def _get_dot_icon(
        self, color: str, opacity: float = 1.0
    ) -> QtGui.QIcon:
        """Tray icon with a colored dot in bottom right corner.

        Args:
            color (str): Color of the dot.
            opacity (float): Opacity of the dot (0.0 - 1.0).

        """
        # Round opacity so the cache does not grow
        opacity = round(opacity, 2)
        key = (color, opacity)
        icon = self._dot_icons.get(key)
        if icon is not None:
            return icon

        size = 128
        # Paint to own pixmap with device pixel ratio 1. Pixmap from
        #   'QIcon.pixmap' has device pixel ratio of the screen (e.g. 1.5
        #   on Windows with display scaling), so painting coordinates
        #   would not match its size and the dot would be out of bounds.
        pix = QtGui.QPixmap(size, size)
        pix.fill(QtCore.Qt.transparent)
        dot_size = size * 0.45
        dot_rect = QtCore.QRectF(
            size - dot_size, size - dot_size, dot_size, dot_size
        )
        painter = QtGui.QPainter(pix)
        painter.setRenderHints(
            QtGui.QPainter.Antialiasing
            | QtGui.QPainter.SmoothPixmapTransform
        )
        painter.drawPixmap(
            QtCore.QRect(0, 0, size, size),
            self._icon.pixmap(size, size),
        )
        outline_color = QtGui.QColor(33, 37, 43)
        pen_width = size * 0.05
        ellipse_rect = dot_rect.adjusted(
            pen_width * 0.5,
            pen_width * 0.5,
            -pen_width * 0.5,
            -pen_width * 0.5,
        )
        # Dark backing (also outline separating the dot from the logo)
        #   fades faster than the color, so half-transparent color is
        #   blended with the backing instead of with the logo
        painter.setOpacity(min(1.0, opacity * 2))
        pen = QtGui.QPen(outline_color)
        pen.setWidthF(pen_width)
        painter.setPen(pen)
        painter.setBrush(outline_color)
        painter.drawEllipse(ellipse_rect)

        painter.setOpacity(opacity)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(color))
        painter.drawEllipse(
            ellipse_rect.adjusted(
                pen_width * 0.5,
                pen_width * 0.5,
                -pen_width * 0.5,
                -pen_width * 0.5,
            )
        )
        painter.end()
        icon = QtGui.QIcon(pix)
        self._dot_icons[key] = icon
        return icon

    @property
    def initializing_addons(self):
        return self._initializing_addons

    def initialize_addons(self):
        self._initializing_addons = True
        try:
            self._tray_manager.initialize_addons()
        finally:
            self._initializing_addons = False
        self._prepare_menu_size()

    def eventFilter(self, obj, event):
        # Ignore mouse clicks on menu right after it was shown. That prevents
        #   to trigger an action (usually 'Exit' as it is under cursor)
        #   by the second click of double-click.
        if obj is self.menu and event.type() in (
            QtCore.QEvent.MouseButtonPress,
            QtCore.QEvent.MouseButtonRelease,
            QtCore.QEvent.MouseButtonDblClick,
        ):
            elapsed_ms = (time.monotonic() - self._menu_shown_at) * 1000
            if elapsed_ms < self.menu_click_guard_ms:
                return True
        return super().eventFilter(obj, event)

    def _on_menu_about_to_show(self):
        self._menu_shown_at = time.monotonic()

    def _on_menu_about_to_hide(self):
        self._menu_hidden_at = time.monotonic()

    def _click_timer_timeout(self):
        self._show_context_menu()

    def _prepare_menu_size(self):
        # Menu is not polished before it is shown for the first time, so its
        #   size is unknown and 'popup' can't place it correctly (it ends up
        #   at the very bottom of the screen instead of above the cursor).
        menu = self.contextMenu()
        menu.ensurePolished()
        menu.adjustSize()

    def _get_menu_pos(self, pos):
        menu = self.contextMenu()
        screen = QtGui.QGuiApplication.screenAt(pos)
        if screen is None:
            screen = QtGui.QGuiApplication.primaryScreen()
        if screen is None:
            return pos

        # Use full screen geometry (not available geometry) so the menu
        #   can overlap the taskbar and opens at the cursor, the same way
        #   as the context menu on right click.
        geo = screen.geometry()
        size = menu.sizeHint()
        x = pos.x()
        y = pos.y()
        # Open menu above/left of the cursor if it does not fit
        #   (tray is usually at the bottom right corner)
        if x + size.width() > geo.right():
            x -= size.width()
        if y + size.height() > geo.bottom():
            y -= size.height()
        x = max(geo.left(), min(x, geo.right() - size.width()))
        y = max(geo.top(), min(y, geo.bottom() - size.height()))
        return QtCore.QPoint(x, y)

    def _show_context_menu(self):
        pos = self._click_pos
        self._click_pos = None
        if pos is None:
            pos = QtGui.QCursor().pos()
        self._prepare_menu_size()
        self.contextMenu().popup(self._get_menu_pos(pos))

    def _on_trigger(self):
        now = time.monotonic()
        # Release of the second click of double-click may also emit
        #   'Trigger' (depends on Qt version)
        if now < self._ignore_trigger_until:
            return

        # Click on tray icon while menu was open closed the menu (on press)
        #   -> don't open it again on release, behave as toggle
        if (now - self._menu_hidden_at) * 1000 < self._doubleclick_time_ms:
            return

        if self.contextMenu().isVisible():
            self.contextMenu().hide()
            return

        self._click_pos = QtGui.QCursor().pos()
        # Wait for possible double-click, then show menu
        self._click_timer.start()

    def _on_doubleclick(self):
        # Cancel pending single click
        self._click_timer.stop()
        self._click_pos = None
        self._ignore_trigger_until = (
            time.monotonic() + (self._doubleclick_time_ms / 1000)
        )
        # Menu might be already visible if the timer timed out before
        #   the second click arrived
        if self.contextMenu().isVisible():
            self.contextMenu().hide()
        self._tray_manager.execute_doubleclick()

    def on_systray_activated(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.Trigger:
            self._on_trigger()

        elif reason == QtWidgets.QSystemTrayIcon.DoubleClick:
            self._on_doubleclick()

    def exit(self):
        """ Exit whole application.

        - Icon won't stay in tray after exit.
        """
        if self._exited:
            return
        self._exited = True

        self._blink_timer.stop()
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


def _fix_macos() -> None:
    """Fix issue with click count on MacOS > 27 for PySide6.

    See '_macos_fix.py' for more details.
    """
    if platform.system().lower() != "darwin":
        return

    # Issue was fixed in Qt 6.12
    if parse(QT_VERSION) >= parse("6.12"):
        return

    try:
        major = int(platform.mac_ver()[0].split(".", 1)[0])
    except (IndexError, ValueError):
        major = -1

    if major < 27:
        return

    install_clickcount_fix()


def main():
    _fix_macos()

    app = get_ayon_qt_app()

    starter = TrayStarter(app)  # noqa F841

    if not is_running_from_build() and os.name == "nt":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            u"ayon_tray"
        )

    sys.exit(app.exec_())
