"""WebServerAddon spawns aiohttp server in asyncio loop.

Main usage of the module is in AYON tray where make sense to add ability
of other modules to add theirs routes. Module which would want use that
option must have implemented method `webserver_initialization` which must
expect `WebServerManager` object where is possible to add routes or paths
with handlers.

WebServerManager is by default created only in tray.

It is possible to create server manager without using module logic at all
using `create_new_server_manager`. That can be handy for standalone scripts
with predefined host and port and separated routes and logic.

Running multiple servers in one process is not recommended and probably won't
work as expected. It is because of few limitations connected to asyncio module.

When module's `create_server_manager` is called it is also set environment
variable "AYON_WEBSERVER_URL". Which should lead to root access point
of server.
"""

import os
import socket

from ayon_core import resources
from ayon_core.addon import AYONAddon, ITrayService

from .version import __version__


class WebServerAddon(AYONAddon, ITrayService):
    name = "webserver"
    version = __version__
    label = "WebServer"

    webserver_url_env = "AYON_WEBSERVER_URL"

    def initialize(self, settings):
        self._server_manager = None
        self._host_listener = None

        self._port = self.find_free_port()
        self._webserver_url = None

    @property
    def server_manager(self):
        """

        Returns:
            Union[WebServerManager, None]: Server manager instance.

        """
        return self._server_manager

    @property
    def port(self):
        """

        Returns:
            int: Port on which is webserver running.

        """
        return self._port

    @property
    def webserver_url(self):
        """

        Returns:
            str: URL to webserver.

        """
        return self._webserver_url

    def connect_with_addons(self, enabled_modules):
        if not self._server_manager:
            return

        for module in enabled_modules:
            if not hasattr(module, "webserver_initialization"):
                continue

            try:
                module.webserver_initialization(self._server_manager)
            except Exception:
                self.log.warning(
                    (
                        "Failed to connect module \"{}\" to webserver."
                    ).format(module.name),
                    exc_info=True
                )

    def tray_init(self):
        self.create_server_manager()
        self._add_resources_statics()
        self._add_listeners()

    def tray_start(self):
        self.start_server()

    def tray_exit(self):
        self.stop_server()

    def start_server(self):
        if self._server_manager is not None:
            self._server_manager.start_server()

    def stop_server(self):
        if self._server_manager is not None:
            self._server_manager.stop_server()

    @staticmethod
    def create_new_server_manager(port=None, host=None):
        """Create webserver manager for passed port and host.

        Args:
            port(int): Port on which wil webserver listen.
            host(str): Host name or IP address. Default is 'localhost'.

        Returns:
            WebServerManager: Prepared manager.
        """
        from .server import WebServerManager

        return WebServerManager(port, host)

    def create_server_manager(self):
        if self._server_manager is not None:
            return

        self._server_manager = self.create_new_server_manager(self._port)
        self._server_manager.on_stop_callbacks.append(
            self.set_service_failed_icon
        )

        webserver_url = self._server_manager.url
        os.environ["OPENPYPE_WEBSERVER_URL"] = str(webserver_url)
        os.environ[self.webserver_url_env] = str(webserver_url)
        self._webserver_url = webserver_url

    @staticmethod
    def find_free_port(
        port_from=None, port_to=None, exclude_ports=None, host=None
    ):
        """Find available socket port from entered range.

        It is also possible to only check if entered port is available.

        Args:
            port_from (int): Port number which is checked as first.
            port_to (int): Last port that is checked in sequence from entered
                `port_from`. Only `port_from` is checked if is not entered.
                Nothing is processed if is equeal to `port_from`!
            exclude_ports (list, tuple, set): List of ports that won't be
                checked form entered range.
            host (str): Host where will check for free ports. Set to
                "localhost" by default.
        """
        if port_from is None:
            port_from = 8079

        if port_to is None:
            port_to = 65535

        # Excluded ports (e.g. reserved for other servers/clients)
        if exclude_ports is None:
            exclude_ports = []

        # Default host is localhost but it is possible to look for other hosts
        if host is None:
            host = "localhost"

        found_port = None
        for port in range(port_from, port_to + 1):
            if port in exclude_ports:
                continue

            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.bind((host, port))
                found_port = port

            except socket.error:
                continue

            finally:
                if sock:
                    sock.close()

            if found_port is not None:
                break

        return found_port

    def _add_resources_statics(self):
        static_prefix = "/res"
        self._server_manager.add_static(static_prefix, resources.RESOURCES_DIR)
        statisc_url = "{}{}".format(
            self._webserver_url, static_prefix
        )

        os.environ["AYON_STATICS_SERVER"] = statisc_url
        os.environ["OPENPYPE_STATICS_SERVER"] = statisc_url

    def _add_listeners(self):
        from . import host_console_listener

        self._host_listener = host_console_listener.HostListener(
            self._server_manager, self
        )
