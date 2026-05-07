import os
import signal
import sys
import threading
import time
import collections
import platform
import threading
from typing import Any, Optional

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
    ITrayAddon,
    ITrayService,
)
from ayon_core.pipeline import install_ayon_plugins
from ayon_core.tools.utils import (
    WrappedCallbackItem,
    get_ayon_qt_app,
)
from ayon_core.tools.tray.lib import (
    set_tray_server_url,
    remove_tray_server_url,
    TrayIsRunningError,
)
from ayon_core.tools.launcher.ui import LauncherWindow
from ayon_core.tools.loader.ui import LoaderWindow
from ayon_core.tools.console_interpreter.ui import ConsoleInterpreterWindow
from ayon_core.tools.publisher.publish_report_viewer import (
    PublishReportViewerWindow,
)

from .addons_manager import TrayAddonsManager  # noqa: E402
from .host_console_listener import HostListener  # noqa: E402
from .info_widget import InfoWidget  # noqa: E402
from .dialogs import (  # noqa: E402
    UpdateDialog,
)

_shutdown_scheduled = False

# True when macOS applicationShouldTerminate_ returns NSTerminateLater;
# main() replies to applicationShouldTerminate after exec_() returns.
_macos_pending_terminate_reply = False


def _request_application_quit():
    """Queue QCoreApplication.quit on the GUI thread.

    Required when shutdown code runs on a worker thread (macOS tray exit path).
    QTimer.singleShot from a non-GUI thread does not reliably post quit() to
    the main thread and can leave timers firing during teardown (crash in
    QTimerInfoList / notifyInternal2 on macOS).
    """
    app = QtCore.QCoreApplication.instance()
    if app is None:
        return
    QtCore.QMetaObject.invokeMethod(
        app,
        "quit",
        QtCore.Qt.ConnectionType.QueuedConnection,
    )


def _dock_dcc_active(dcc_companion: bool, dcc_host_pid: int) -> bool:
    """True when DCC companion requests Darwin PID-targeted tray commands."""
    return (
        bool(dcc_companion)
        and int(dcc_host_pid) > 0
        and platform.system() == "Darwin"
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

        self._launcher_window = None
        self._browser_window = None
        self._publisher_window = None
        self._workfiles_window = None
        self._scene_inventory_window = None
        self._dock_shim_quit_urls: dict[str, str] = {}
        self._dock_suppress_shim_quit: set[str] = set()
        self._dock_close_filter = None

        self._console_window = None
        self._publish_report_viewer_window = None

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
            set_tray_server_url(self._addons_manager.webserver_url, False)
        except TrayIsRunningError:
            self.log.error("Tray is already running.")
            self._closing = True

    def is_closing(self):
        return self._closing

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
        launcher_action = QtWidgets.QAction("Launcher", tray_menu)
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
        browser_action = QtWidgets.QAction("Browser", tray_menu)
        browser_action.triggered.connect(self._show_browser_window)
        tray_menu.addAction(browser_action)

        self._addons_manager.add_route("GET", "/tray", self._web_get_tray_info)
        self._addons_manager.add_route(
            "POST", "/tray/message", self._web_show_tray_message
        )

        from ayon_core.tools.tool_icon_wrapper import register_tray_routes

        register_tray_routes(self._addons_manager, self)

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
        exit_action.triggered.connect(self._confirm_exit_from_menu)
        tray_menu.addAction(exit_action)

        # Tell each addon which addons were imported
        # TODO Capture only webserver issues (the only thing that can crash).
        try:
            self._addons_manager.start_addons()
        except Exception:
            self.log.error("Failed to start addons.", exc_info=True)
            return self.exit()

        # Print time report
        self._addons_manager.print_report()

        self._main_thread_timer.start()

        if self._update_check_interval > 0:
            self._update_check_timer.start()

        self.execute_in_main_thread(self._startup_validations)
        try:
            set_tray_server_url(self._addons_manager.webserver_url, True)
        except TrayIsRunningError:
            self.log.warning("Other tray started meanwhile. Exiting.")
            self.exit()

        if platform.system() == "Darwin":
            # Run on the tray thread so plist / codesign finish before UI settles;
            # Dock shim build stays in a background thread (can be slow).
            try:
                from ayon_core.tools.tray.ensure_main_bundle_lsuielement import (
                    try_patch_main_bundle_lsuielement,
                )

                try_patch_main_bundle_lsuielement()
            except Exception:  # noqa: BLE001
                self.log.warning(
                    "ensure_main_bundle_lsuielement failed.",
                    exc_info=True,
                )

            def _dock_shim_autoinstall_worker() -> None:
                try:
                    from ayon_core.tools.tray import dock_shim_installer

                    dock_shim_installer.try_auto_install_dock_shim_bundles()
                except Exception:  # noqa: BLE001
                    self.log.debug(
                        "Dock shim auto-installer failed.",
                        exc_info=True,
                    )

            threading.Thread(
                target=_dock_shim_autoinstall_worker,
                name="AyonDockShimAutoinstall",
                daemon=True,
            ).start()

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

    def _confirm_exit_from_menu(self):
        reply = QtWidgets.QMessageBox.question(
            self.main_window,
            "Close AYON",
            "Are you sure you want to close AYON?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply == QtWidgets.QMessageBox.Yes:
            self.tray_widget.exit()

    def exit(self):
        self._closing = True
        if self._main_thread_timer.isActive():
            self.execute_in_main_thread(self.tray_widget.exit)
        else:
            self.tray_widget.exit()

    def stop_timers(self):
        """Stop all TrayManager timers so no callbacks run during shutdown."""
        if self._main_thread_timer.isActive():
            self._main_thread_timer.stop()
        if self._update_check_timer.isActive():
            self._update_check_timer.stop()

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

        return json_response(
            {
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
                "tray_base_url": self._addons_manager.webserver_url,
            }
        )

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

    async def _web_dock_open_or_focus(
        self, request: Request
    ) -> Response:
        from ayon_core.tools.tray import tool_shim

        if not tool_shim.request_authorized(request):
            return tool_shim.unauthorized_json()
        data = await request.json()
        tool_name = data.get("tool")
        if tool_name not in tool_shim.DOCK_TOOL_KEYS:
            return json_response(
                {"success": False, "error": "unknown tool"},
                status=400,
            )
        shim_quit_url = data.get("shim_quit_url")
        dcc_companion = bool(data.get(tool_shim.DCC_COMPANION_JSON))
        dcc_host_pid = int(data.get(tool_shim.DCC_HOST_PID_JSON) or 0)
        if dcc_companion and dcc_host_pid <= 0:
            return json_response(
                {
                    "success": False,
                    "error": "invalid dcc_host_pid for dcc_companion",
                },
                status=400,
            )
        self.log.debug(
            "Dock HTTP: open_or_focus tool=%s shim_quit=%s dcc=%s dcc_pid=%s",
            tool_name,
            bool(shim_quit_url),
            dcc_companion,
            dcc_host_pid if dcc_companion else 0,
        )
        self.execute_in_main_thread(
            self._dock_open_or_focus_sync,
            tool_name,
            shim_quit_url,
            dcc_companion,
            dcc_host_pid,
        )
        return json_response({"success": True})

    async def _web_dock_focus(self, request: Request) -> Response:
        from ayon_core.tools.tray import tool_shim

        if not tool_shim.request_authorized(request):
            return tool_shim.unauthorized_json()
        data = await request.json()
        tool_name = data.get("tool")
        if tool_name not in tool_shim.DOCK_TOOL_KEYS:
            return json_response(
                {"success": False, "error": "unknown tool"},
                status=400,
            )
        dcc_companion = bool(data.get(tool_shim.DCC_COMPANION_JSON))
        dcc_host_pid = int(data.get(tool_shim.DCC_HOST_PID_JSON) or 0)
        if dcc_companion and dcc_host_pid <= 0:
            return json_response(
                {
                    "success": False,
                    "error": "invalid dcc_host_pid for dcc_companion",
                },
                status=400,
            )
        self.log.debug(
            "Dock HTTP: focus tool=%s dcc=%s dcc_pid=%s",
            tool_name,
            dcc_companion,
            dcc_host_pid if dcc_companion else 0,
        )
        self.execute_in_main_thread(
            self._dock_focus_sync, tool_name, dcc_companion, dcc_host_pid
        )
        return json_response({"success": True})

    async def _web_dock_close_from_shim(self, request: Request) -> Response:
        from ayon_core.tools.tray import tool_shim

        if not tool_shim.request_authorized(request):
            return tool_shim.unauthorized_json()
        data = await request.json()
        tool_name = data.get("tool")
        if tool_name not in tool_shim.DOCK_TOOL_KEYS:
            return json_response(
                {"success": False, "error": "unknown tool"},
                status=400,
            )
        dcc_companion = bool(data.get(tool_shim.DCC_COMPANION_JSON))
        dcc_host_pid = int(data.get(tool_shim.DCC_HOST_PID_JSON) or 0)
        if dcc_companion and dcc_host_pid <= 0:
            return json_response(
                {
                    "success": False,
                    "error": "invalid dcc_host_pid for dcc_companion",
                },
                status=400,
            )
        self.log.debug(
            "Dock HTTP: close_from_shim tool=%s dcc=%s dcc_pid=%s",
            tool_name,
            dcc_companion,
            dcc_host_pid if dcc_companion else 0,
        )
        done = threading.Event()
        exc_holder: list[BaseException] = []

        def _cb() -> None:
            try:
                self._dock_close_from_shim_sync(
                    tool_name, dcc_companion, dcc_host_pid
                )
            except BaseException as e:
                exc_holder.append(e)
            finally:
                done.set()

        self.execute_in_main_thread(_cb)
        if not done.wait(timeout=5.0):
            return json_response(
                {"success": False, "error": "timeout waiting for main thread"},
                status=500,
            )
        if exc_holder:
            return json_response(
                {"success": False, "error": str(exc_holder[0])},
                status=500,
            )
        return json_response({"success": True})

    def _tool_window(self, tool_name: str) -> Optional[QtWidgets.QWidget]:
        return {
            "launcher": self._launcher_window,
            "loader": self._browser_window,
            "publisher": self._publisher_window,
            "workfiles": self._workfiles_window,
            "scene_inventory": self._scene_inventory_window,
        }.get(tool_name)

    def _dock_close_from_shim_sync(
        self,
        tool_name: str,
        dcc_companion: bool = False,
        dcc_host_pid: int = 0,
    ) -> None:
        from ayon_core.tools.tray import tool_shim

        if _dock_dcc_active(dcc_companion, dcc_host_pid):
            tool_shim.write_close_request(dcc_host_pid, tool_name)
            return
        self._dock_suppress_shim_quit.add(tool_name)
        try:
            win = self._tool_window(tool_name)
            if win is not None:
                win.close()
                app = get_ayon_qt_app()
                if app is not None:
                    app.processEvents()
            else:
                self._dock_suppress_shim_quit.discard(tool_name)
        except BaseException:
            self._dock_suppress_shim_quit.discard(tool_name)
            raise

    def _register_dock_tool_window(
        self, widget: QtWidgets.QWidget, tool_name: str
    ) -> None:
        from ayon_core.tools.tray import tool_shim
        from ayon_core.tools.tool_icon_wrapper import taskbar_identity

        if self._dock_close_filter is None:
            self._dock_close_filter = tool_shim.ShimCloseFilter(
                self._on_dock_tool_closed
            )
            self._dock_close_filter.setParent(self.main_window)
        self._dock_close_filter.register_widget(widget, tool_name)
        widget.installEventFilter(self._dock_close_filter)
        taskbar_identity.set_taskbar_identity(widget, tool_name)

    def _on_dock_tool_closed(self, tool_name: str) -> None:
        from ayon_core.tools.tray import tool_shim

        if tool_name in self._dock_suppress_shim_quit:
            self._dock_suppress_shim_quit.discard(tool_name)
            self._dock_shim_quit_urls.pop(tool_name, None)
            self.log.debug(
                "Dock: tool closed (shim) tool=%s — skip quit post",
                tool_name,
            )
            return
        url = self._dock_shim_quit_urls.pop(tool_name, None)
        self.log.debug(
            "Dock: tool window closed tool=%s shim_quit=%s",
            tool_name,
            bool(url),
        )
        if not url:
            self.log.debug(
                "Dock: tool closed with no paired shim (no quit URL).",
            )
        tool_shim.post_shim_quit_async(url)

    def _dock_open_or_focus_sync(
        self,
        tool_name: str,
        shim_quit_url: Optional[str],
        dcc_companion: bool = False,
        dcc_host_pid: int = 0,
    ) -> None:
        from ayon_core.tools.tray import tool_shim

        self.log.debug("Dock: open_or_focus_sync tool=%s", tool_name)
        if _dock_dcc_active(dcc_companion, dcc_host_pid):
            tool_shim.activate_pid(dcc_host_pid)
            return
        if shim_quit_url:
            self._dock_shim_quit_urls[tool_name] = shim_quit_url
        if tool_name == "launcher":
            self._present_launcher(allow_shim=False)
        elif tool_name == "loader":
            self._present_loader(allow_shim=False)
        elif tool_name == "publisher":
            self._present_publisher(allow_shim=False)
        elif tool_name == "workfiles":
            w = self._get_or_create_workfiles_window()
            w.ensure_visible(
                use_context=False,
                save=True,
                on_top=False,
            )
        elif tool_name == "scene_inventory":
            w = self._get_or_create_scene_inventory_window()
            w.show()
            w.refresh()
            w.raise_()
            w.activateWindow()
            w.showNormal()
        self._dock_focus_top_window_for_tool(tool_name, False, 0)

    def _dock_focus_sync(
        self,
        tool_name: str,
        dcc_companion: bool = False,
        dcc_host_pid: int = 0,
    ) -> None:
        from ayon_core.tools.tray import tool_shim

        if _dock_dcc_active(dcc_companion, dcc_host_pid):
            tool_shim.activate_pid(dcc_host_pid)
            return
        if platform.system() == "Darwin":
            tool_shim.activate_pid(os.getpid())
        self._dock_focus_top_window_for_tool(tool_name, False, 0)

    def _dock_focus_top_window_for_tool(
        self,
        tool_name: str,
        dcc_companion: bool = False,
        dcc_host_pid: int = 0,
    ) -> None:
        from ayon_core.tools.tray import tool_shim

        if _dock_dcc_active(dcc_companion, dcc_host_pid):
            tool_shim.activate_pid(dcc_host_pid)
            return
        win = self._tool_window(tool_name)
        if win is None:
            self._dock_open_or_focus_sync(tool_name, None, False, 0)
            return
        if tool_name == "publisher" and hasattr(win, "make_sure_is_visible"):
            win.make_sure_is_visible()
        elif tool_name == "workfiles" and hasattr(win, "ensure_visible"):
            win.ensure_visible(
                use_context=False,
                save=True,
                on_top=False,
            )
        elif tool_name == "scene_inventory" and hasattr(win, "refresh"):
            win.refresh()
        win.show()
        win.raise_()
        win.activateWindow()
        win.showNormal()

    def _get_or_create_publisher_window(self):
        from ayon_core.tools.publisher.window import PublisherWindow

        try:
            from ayon_traypublisher.api import tray_dock
        except ImportError:
            tray_dock = None
        if tray_dock is not None and tray_dock.is_traypublisher_tray_enabled(
            self
        ):
            return tray_dock.get_or_create_publisher_in_tray(self)
        if self._publisher_window is None:
            install_ayon_plugins()
            pub_parent = None if sys.platform == "win32" else self.main_window
            self._publisher_window = PublisherWindow(parent=pub_parent)
            self._register_dock_tool_window(
                self._publisher_window, "publisher"
            )
        return self._publisher_window

    def _get_or_create_workfiles_window(self):
        from ayon_core.tools.workfiles.widgets.window import (
            WorkfilesToolWindow,
        )

        if self._workfiles_window is None:
            self._workfiles_window = WorkfilesToolWindow(
                parent=self.main_window
            )
            self._register_dock_tool_window(
                self._workfiles_window, "workfiles"
            )
        return self._workfiles_window

    def _get_or_create_scene_inventory_window(self) -> Any:
        if self._scene_inventory_window is None:
            from ayon_core.tools.sceneinventory.window import (
                SceneInventoryWindow,
            )

            install_ayon_plugins()
            self._scene_inventory_window = SceneInventoryWindow(
                parent=self.main_window
            )
            self._register_dock_tool_window(
                self._scene_inventory_window, "scene_inventory"
            )
        return self._scene_inventory_window

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
            "stagingBundle" if is_staging_enabled() else "productionBundle"
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
            ),
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
        tray_menu.addSeparator()
        if is_dev_mode_enabled():
            bundle_type_label = os.getenv("AYON_BUNDLE_NAME")
        elif is_staging_enabled():
            bundle_type_label = "Staging"
        else:
            bundle_type_label = "Production"
        launcher_version = os.getenv("AYON_VERSION", "AYON Info")
        version_string = (
            f"{bundle_type_label} | AYON: {launcher_version}"
        )

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
            self._show_ayon_login, restart_on_token_change=True
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
        self._present_launcher(allow_shim=True)

    def _present_launcher(self, *, allow_shim: bool) -> None:
        from ayon_core.tools.tray import tool_shim

        if allow_shim and tool_shim.open_shim_for_tool("launcher"):
            return
        if self._launcher_window is None:
            self._launcher_window = LauncherWindow()
            self._register_dock_tool_window(self._launcher_window, "launcher")

        self._launcher_window.show()
        self._launcher_window.raise_()
        self._launcher_window.activateWindow()

    def _show_browser_window(self):
        self._present_loader(allow_shim=True)

    def _present_loader(self, *, allow_shim: bool) -> None:
        from ayon_core.tools.tray import tool_shim

        if allow_shim and tool_shim.open_shim_for_tool("loader"):
            return
        if self._browser_window is None:
            self._browser_window = LoaderWindow()
            self._browser_window.setWindowTitle("AYON Browser")
            install_ayon_plugins()
            self._register_dock_tool_window(self._browser_window, "loader")

        self._browser_window.show()
        self._browser_window.raise_()
        self._browser_window.activateWindow()

    def open_publisher_tool(self) -> None:
        """Open Publisher from a tray menu action (``ITrayAction``)."""
        self._present_publisher(allow_shim=True)

    def _present_publisher(self, *, allow_shim: bool) -> None:
        from ayon_core.tools.tray import tool_shim

        if allow_shim and tool_shim.open_shim_for_tool("publisher"):
            return
        pub = self._get_or_create_publisher_window()
        if hasattr(pub, "make_sure_is_visible"):
            pub.make_sure_is_visible()
        else:
            pub.show()
            pub.raise_()
            pub.activateWindow()
            pub.showNormal()

    def _show_console_window(self):
        if self._console_window is None:
            self._console_window = ConsoleInterpreterWindow()
        self._console_window.show()
        self._console_window.raise_()
        self._console_window.activateWindow()

    def _show_publish_report_viewer(self):
        if self._publish_report_viewer_window is None:
            self._publish_report_viewer_window = PublishReportViewerWindow()
        self._publish_report_viewer_window.refresh()
        self._publish_report_viewer_window.show()
        self._publish_report_viewer_window.raise_()
        self._publish_report_viewer_window.activateWindow()


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
        """Exit whole application.

        - If called from a non-main thread, skip Qt and force exit.
        - On macOS, skip self.hide(): tray icon cleanup can block the main
          thread and deadlock when exit() runs on the main thread.
        - Run blocking cleanup in a worker thread; schedule
          QCoreApplication.exit() when done.
        """
        if self._exited:
            return
        self._exited = True
        if threading.current_thread() is not threading.main_thread():
            os._exit(0)
        if platform.system() != "Darwin":
            self.hide()

        starter = getattr(self, "_tray_starter", None)
        if starter is not None:
            start_timer = getattr(starter, "_start_timer", None)
            if start_timer is not None and start_timer.isActive():
                start_timer.stop()

        self._tray_manager.stop_timers()
        remove_tray_server_url()

        def cleanup_then_quit():
            self._tray_manager._addons_manager.on_exit()
            _request_application_quit()

        worker = threading.Thread(target=cleanup_then_quit, daemon=True)
        worker.start()


def _install_macos_terminate_handler(tray_widget):
    """Install NSApplication delegate for Cmd+Q / dock Quit on Darwin."""
    global _macos_pending_terminate_reply
    if platform.system() != "Darwin":
        return
    try:
        import AppKit
        import objc

        NSApp = AppKit.NSApplication.sharedApplication()
        # NSTerminateLater = 2
        NSTerminateLater = 2

        class TerminateDelegate(objc.lookUpClass("NSObject")):
            def applicationShouldTerminate_(self, sender):
                global _macos_pending_terminate_reply
                _macos_pending_terminate_reply = True
                QtCore.QTimer.singleShot(0, tray_widget.exit)
                return NSTerminateLater

        delegate = TerminateDelegate.alloc().init()
        NSApp.setDelegate_(delegate)
    except Exception:
        pass


class _AppQuitEventFilter(QtCore.QObject):
    """Catch app-level Close and Quit (dock Quit / Cmd+Q on macOS)."""

    def __init__(self, tray_widget, app, main_window=None):
        super(_AppQuitEventFilter, self).__init__()
        self._tray_widget = tray_widget
        self._app = app
        self._main_window = main_window

    def eventFilter(self, obj, event):
        # On macOS, Cmd+Q posts QEvent.Quit to the app, not Close.
        if event.type() == QtCore.QEvent.Quit and obj is self._app:
            self._tray_widget.exit()
            return super(_AppQuitEventFilter, self).eventFilter(obj, event)
        if event.type() != QtCore.QEvent.Close:
            return super(_AppQuitEventFilter, self).eventFilter(obj, event)
        if obj is self._app:
            self._tray_widget.exit()
            return super(_AppQuitEventFilter, self).eventFilter(obj, event)
        # macOS: dock Quit / Cmd+Q may deliver Close to the tray parent window.
        if self._main_window is not None and obj is self._main_window:
            self._tray_widget.exit()
        return super(_AppQuitEventFilter, self).eventFilter(obj, event)


def _make_signal_exit_handler(tray_widget):
    def _handler(*args):
        global _shutdown_scheduled
        if _shutdown_scheduled:
            return
        _shutdown_scheduled = True
        QtCore.QTimer.singleShot(0, tray_widget.exit)

    return _handler


class TrayStarter(QtCore.QObject):
    def __init__(self, app):
        super(TrayStarter, self).__init__(None)
        app.setQuitOnLastWindowClosed(False)
        self._app = app
        self._splash = None

        main_window = QtWidgets.QMainWindow()
        tray_widget = SystemTrayIcon(main_window)
        tray_widget._tray_starter = self

        app.aboutToQuit.connect(tray_widget.exit)
        self._quit_event_filter = _AppQuitEventFilter(
            tray_widget, app, main_window=main_window
        )
        app.installEventFilter(self._quit_event_filter)
        _install_macos_terminate_handler(tray_widget)

        if os.name != "nt":
            handler = _make_signal_exit_handler(tray_widget)
            signal.signal(signal.SIGTERM, handler)
            signal.signal(signal.SIGINT, handler)

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
    # Qt 6.7.3+ macOS: menu icons default off; launcher may have created
    # QApplication already — clear before and after we obtain the app.
    _no_hide_icons = getattr(QtCore.Qt, "AA_DontShowIconsInMenus", None)
    if _no_hide_icons is not None:
        QtCore.QCoreApplication.setAttribute(_no_hide_icons, False)

    app = get_ayon_qt_app()

    if _no_hide_icons is not None:
        QtCore.QCoreApplication.setAttribute(_no_hide_icons, False)

    starter = TrayStarter(app)  # noqa F841

    if not is_running_from_build() and os.name == "nt":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "ayon_tray"
        )

    exit_code = app.exec_()
    if platform.system() == "Darwin":
        if _macos_pending_terminate_reply:
            try:
                import AppKit

                AppKit.NSApplication.sharedApplication().replyToApplicationShouldTerminate_(
                    True
                )
            except Exception:
                pass
        log = Logger.get_logger("TrayMain")

        def _macos_force_exit():
            time.sleep(5)
            log.warning("macOS exit timeout; forcing process exit")
            os._exit(exit_code)

        t = threading.Thread(target=_macos_force_exit, daemon=True)
        t.start()
    sys.exit(exit_code)
