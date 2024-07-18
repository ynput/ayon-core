"""TrayWebserver spawns aiohttp server in asyncio loop.

Usage is to add ability to register routes from addons, or for inner calls
of tray. Addon which would want use that option must have implemented method
webserver_initialization` which must expect `WebServerManager` object where
is possible to add routes or paths with handlers.

WebServerManager is by default created only in tray.

Running multiple servers in one process is not recommended and probably won't
work as expected. It is because of few limitations connected to asyncio module.
"""

import os
import socket
from typing import Callable

from ayon_core import resources
from ayon_core.lib import Logger

from .server import WebServerManager
from .host_console_listener import HostListener


class TrayWebserver:
    webserver_url_env = "AYON_WEBSERVER_URL"

    def __init__(self, tray_manager):
        self._log = None
        self._tray_manager = tray_manager
        self._port = self.find_free_port()

        self._server_manager = WebServerManager(self._port, None)

        webserver_url = self._server_manager.url
        self._webserver_url = webserver_url

        self._host_listener = HostListener(self, self._tray_manager)

        static_prefix = "/res"
        self._server_manager.add_static(static_prefix, resources.RESOURCES_DIR)
        statisc_url = "{}{}".format(
            webserver_url, static_prefix
        )

        os.environ[self.webserver_url_env] = str(webserver_url)
        os.environ["AYON_STATICS_SERVER"] = statisc_url

        # Deprecated
        os.environ["OPENPYPE_WEBSERVER_URL"] = str(webserver_url)
        os.environ["OPENPYPE_STATICS_SERVER"] = statisc_url

    @property
    def log(self):
        if self._log is None:
            self._log = Logger.get_logger("TrayWebserver")
        return self._log

    def add_route(self, request_method: str, path: str, handler: Callable):
        self._server_manager.add_route(request_method, path, handler)

    def add_static(self, prefix: str, path: str):
        self._server_manager.add_static(prefix, path)

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

    def connect_with_addons(self, enabled_addons):
        if not self._server_manager:
            return

        for addon in enabled_addons:
            if not hasattr(addon, "webserver_initialization"):
                continue

            try:
                addon.webserver_initialization(self._server_manager)
            except Exception:
                self.log.warning(
                    f"Failed to connect addon \"{addon.name}\" to webserver.",
                    exc_info=True
                )

    def start(self):
        self._start_server()

    def stop(self):
        self._stop_server()

    def _start_server(self):
        if self._server_manager is not None:
            self._server_manager.start_server()

    def _stop_server(self):
        if self._server_manager is not None:
            self._server_manager.stop_server()

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
