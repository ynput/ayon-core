import re
import threading
import asyncio
import socket
import random
from typing import Callable, Optional

from aiohttp import web

from ayon_core.lib import Logger
from ayon_core.resources import RESOURCES_DIR

from .cors_middleware import cors_middleware


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
            "0.0.0.0" by default.
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
        host = "0.0.0.0"

    found_port = None
    while True:
        port = random.randint(port_from, port_to)
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


class WebServerManager:
    """Manger that care about web server thread."""

    def __init__(
        self, port: Optional[int] = None, host: Optional[str] = None
    ):
        self._log = None

        self.port = port or 8079
        self.host = host or "0.0.0.0"

        self.on_stop_callbacks = []

        self.app = web.Application(
            middlewares=[
                cors_middleware(
                    origins=[re.compile(r"^https?\:\/\/localhost")]
                )
            ]
        )

        # add route with multiple methods for single "external app"
        self.webserver_thread = WebServerThread(self)

        self.add_static("/res", RESOURCES_DIR)

    @property
    def log(self):
        if self._log is None:
            self._log = Logger.get_logger(self.__class__.__name__)
        return self._log

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def add_route(self, request_method: str, path: str, handler: Callable):
        self.app.router.add_route(request_method, path, handler)

    def add_static(self, prefix: str, path: str):
        self.app.router.add_static(prefix, path)

    def add_addon_route(
        self,
        addon_name: str,
        path: str,
        request_method: str,
        handler: Callable
    ) -> str:
        path = path.lstrip("/")
        full_path = f"/addons/{addon_name}/{path}"
        self.app.router.add_route(request_method, full_path, handler)
        return full_path

    def add_addon_static(
        self, addon_name: str, prefix: str, path: str
    ) -> str:
        full_path = f"/addons/{addon_name}/{prefix}"
        self.app.router.add_static(full_path, path)
        return full_path

    def connect_with_addons(self, addons):
        for addon in addons:
            if not hasattr(addon, "webserver_initialization"):
                continue

            try:
                addon.webserver_initialization(self)
            except Exception:
                self.log.warning(
                    f"Failed to connect addon \"{addon.name}\" to webserver.",
                    exc_info=True
                )

    def start_server(self):
        if self.webserver_thread and not self.webserver_thread.is_alive():
            self.webserver_thread.start()

    def stop_server(self):
        if not self.is_running:
            return
        try:
            self.log.debug("Stopping Web server")
            self.webserver_thread.is_running = False
            self.webserver_thread.stop()

        except Exception:
            self.log.warning(
                "Error has happened during Killing Web server",
                exc_info=True
            )

    @property
    def is_running(self) -> bool:
        if not self.webserver_thread:
            return False
        return self.webserver_thread.is_running

    def thread_stopped(self):
        for callback in self.on_stop_callbacks:
            callback()


class WebServerThread(threading.Thread):
    """ Listener for requests in thread."""

    def __init__(self, manager):
        self._log = None

        super(WebServerThread, self).__init__()

        self.is_running = False
        self.manager = manager
        self.loop = None
        self.runner = None
        self.site = None
        self.tasks = []

    @property
    def log(self):
        if self._log is None:
            self._log = Logger.get_logger(self.__class__.__name__)
        return self._log

    @property
    def port(self):
        return self.manager.port

    @property
    def host(self):
        return self.manager.host

    def run(self):
        self.is_running = True

        try:
            self.log.info("Starting WebServer server")
            self.loop = asyncio.new_event_loop()  # create new loop for thread
            asyncio.set_event_loop(self.loop)

            self.loop.run_until_complete(self.start_server())

            self.log.debug(
                "Running Web server on URL: \"localhost:{}\"".format(self.port)
            )

            asyncio.ensure_future(self.check_shutdown(), loop=self.loop)
            self.loop.run_forever()

        except Exception:
            self.log.warning(
                "Web Server service has failed", exc_info=True
            )
        finally:
            self.loop.close()  # optional

        self.is_running = False
        self.manager.thread_stopped()
        self.log.info("Web server stopped")

    async def start_server(self):
        """ Starts runner and TCPsite """
        self.runner = web.AppRunner(self.manager.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()

    def stop(self):
        """Sets is_running flag to false, 'check_shutdown' shuts server down"""
        self.is_running = False

    async def check_shutdown(self):
        """ Future that is running and checks if server should be running
            periodically.
        """
        while self.is_running:
            while self.tasks:
                task = self.tasks.pop(0)
                self.log.debug("waiting for task {}".format(task))
                await task
                self.log.debug("returned value {}".format(task.result))

            await asyncio.sleep(0.5)

        self.log.debug("Starting shutdown")
        await self.site.stop()
        self.log.debug("Site stopped")
        await self.runner.cleanup()
        self.log.debug("Runner stopped")
        tasks = [
            task
            for task in asyncio.all_tasks()
            if task is not asyncio.current_task()
        ]
        list(map(lambda task: task.cancel(), tasks))  # cancel all the tasks
        results = await asyncio.gather(*tasks, return_exceptions=True)
        self.log.debug(
            f'Finished awaiting cancelled tasks, results: {results}...'
        )
        await self.loop.shutdown_asyncgens()
        # to really make sure everything else has time to stop
        await asyncio.sleep(0.07)
        self.loop.stop()
