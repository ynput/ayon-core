import os
import time
from typing import Callable

from ayon_core.addon import AddonsManager, ITrayAddon, ITrayService
from ayon_core.tools.tray.webserver import (
    find_free_port,
    WebServerManager,
)


class TrayAddonsManager(AddonsManager):
    # TODO do not use env variable
    webserver_url_env = "AYON_WEBSERVER_URL"
    # Define order of addons in menu
    # TODO find better way how to define order
    addons_menu_order = (
        "ftrack",
        "kitsu",
        "launcher_tool",
        "clockify",
    )

    def __init__(self, tray_manager):
        super().__init__(initialize=False)

        self._tray_manager = tray_manager

        self._webserver_manager = WebServerManager(find_free_port(), None)

        self.doubleclick_callbacks = {}
        self.doubleclick_callback = None

    @property
    def webserver_url(self):
        return self._webserver_manager.url

    def get_doubleclick_callback(self):
        callback_name = self.doubleclick_callback
        return self.doubleclick_callbacks.get(callback_name)

    def add_doubleclick_callback(self, addon, callback):
        """Register double-click callbacks on tray icon.

        Currently, there is no way how to determine which is launched. Name of
        callback can be defined with `doubleclick_callback` attribute.

        Missing feature how to define default callback.

        Args:
            addon (AYONAddon): Addon object.
            callback (FunctionType): Function callback.
        """

        callback_name = "_".join([addon.name, callback.__name__])
        if callback_name not in self.doubleclick_callbacks:
            self.doubleclick_callbacks[callback_name] = callback
            if self.doubleclick_callback is None:
                self.doubleclick_callback = callback_name
            return

        self.log.warning((
            "Callback with name \"{}\" is already registered."
        ).format(callback_name))

    def initialize(self, tray_menu):
        self.initialize_addons()
        self.tray_init()
        self.connect_addons()
        self.tray_menu(tray_menu)

    def add_route(self, request_method: str, path: str, handler: Callable):
        self._webserver_manager.add_route(request_method, path, handler)

    def add_static(self, prefix: str, path: str):
        self._webserver_manager.add_static(prefix, path)

    def add_addon_route(
        self,
        addon_name: str,
        path: str,
        request_method: str,
        handler: Callable
    ) -> str:
        return self._webserver_manager.add_addon_route(
            addon_name,
            path,
            request_method,
            handler
        )

    def add_addon_static(
        self, addon_name: str, prefix: str, path: str
    ) -> str:
        return self._webserver_manager.add_addon_static(
            addon_name,
            prefix,
            path
        )

    def get_enabled_tray_addons(self):
        """Enabled tray addons.

        Returns:
            list[AYONAddon]: Enabled addons that inherit from tray interface.
        """

        return [
            addon
            for addon in self.get_enabled_addons()
            if isinstance(addon, ITrayAddon)
        ]

    def restart_tray(self):
        if self._tray_manager:
            self._tray_manager.restart()

    def tray_init(self):
        self._init_tray_webserver()
        report = {}
        time_start = time.time()
        prev_start_time = time_start
        for addon in self.get_enabled_tray_addons():
            try:
                addon._tray_manager = self._tray_manager
                addon.tray_init()
                addon.tray_initialized = True
            except Exception:
                self.log.warning(
                    "Addon \"{}\" crashed on `tray_init`.".format(
                        addon.name
                    ),
                    exc_info=True
                )

            now = time.time()
            report[addon.__class__.__name__] = now - prev_start_time
            prev_start_time = now

        if self._report is not None:
            report[self._report_total_key] = time.time() - time_start
            self._report["Tray init"] = report

    def connect_addons(self):
        self._webserver_manager.connect_with_addons(
            self.get_enabled_addons()
        )
        super().connect_addons()

    def tray_menu(self, tray_menu):
        ordered_addons = []
        enabled_by_name = {
            addon.name: addon
            for addon in self.get_enabled_tray_addons()
        }

        for name in self.addons_menu_order:
            addon_by_name = enabled_by_name.pop(name, None)
            if addon_by_name:
                ordered_addons.append(addon_by_name)
        ordered_addons.extend(enabled_by_name.values())

        report = {}
        time_start = time.time()
        prev_start_time = time_start
        for addon in ordered_addons:
            if not addon.tray_initialized:
                continue

            try:
                addon.tray_menu(tray_menu)
            except Exception:
                # Unset initialized mark
                addon.tray_initialized = False
                self.log.warning(
                    "Addon \"{}\" crashed on `tray_menu`.".format(
                        addon.name
                    ),
                    exc_info=True
                )
            now = time.time()
            report[addon.__class__.__name__] = now - prev_start_time
            prev_start_time = now

        if self._report is not None:
            report[self._report_total_key] = time.time() - time_start
            self._report["Tray menu"] = report

    def start_addons(self):
        self._webserver_manager.start_server()

        report = {}
        time_start = time.time()
        prev_start_time = time_start
        for addon in self.get_enabled_tray_addons():
            if not addon.tray_initialized:
                if isinstance(addon, ITrayService):
                    addon.set_service_failed_icon()
                continue

            try:
                addon.tray_start()
            except Exception:
                self.log.warning(
                    "Addon \"{}\" crashed on `tray_start`.".format(
                        addon.name
                    ),
                    exc_info=True
                )
            now = time.time()
            report[addon.__class__.__name__] = now - prev_start_time
            prev_start_time = now

        if self._report is not None:
            report[self._report_total_key] = time.time() - time_start
            self._report["Addons start"] = report

    def on_exit(self):
        self._webserver_manager.stop_server()
        for addon in self.get_enabled_tray_addons():
            if addon.tray_initialized:
                try:
                    addon.tray_exit()
                except Exception:
                    self.log.warning(
                        "Addon \"{}\" crashed on `tray_exit`.".format(
                            addon.name
                        ),
                        exc_info=True
                    )

    def get_tray_webserver(self):
        # TODO rename/remove method
        return self._webserver_manager

    def _init_tray_webserver(self):
        webserver_url = self.webserver_url
        statics_url = f"{webserver_url}/res"

        # Deprecated
        # TODO stop using these env variables
        # - function 'get_tray_server_url' should be used instead
        os.environ[self.webserver_url_env] = webserver_url
        os.environ["AYON_STATICS_SERVER"] = statics_url
