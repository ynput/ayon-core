import json
import logging
from concurrent.futures import CancelledError

import aiohttp
from aiohttp import web
from qtpy import QtWidgets

from ayon_core.addon import ITrayService
from ayon_core.tools.stdout_broker.window import ConsoleDialog

from ayon_core.tools.tray import HostMsgAction

log = logging.getLogger(__name__)


# Host listener icon type
class IconType:
    IDLE = "idle"
    RUNNING = "running"
    FAILED = "failed"


class HostListener:
    def __init__(self, addons_manager, tray_manager):
        self._tray_manager = tray_manager
        self._window_per_id = {}  # dialogs per host name
        self._action_per_id = {}  # QAction per host name

        addons_manager.add_route(
            "*", "/ws/host_listener", self.websocket_handler
        )

    def _host_is_connecting(self, host_name, label):
        """ Initialize dialog, adds to submenu."""
        ITrayService.services_submenu(self._tray_manager)
        services_submenu = self._tray_manager.get_services_submenu()
        action = QtWidgets.QAction(label, services_submenu)
        action.triggered.connect(lambda: self.show_widget(host_name))

        services_submenu.addAction(action)
        self._action_per_id[host_name] = action
        self._set_host_icon(host_name, IconType.IDLE)
        widget = ConsoleDialog("")
        self._window_per_id[host_name] = widget

    def _set_host_icon(self, host_name, icon_type):
        """Assigns icon to action for 'host_name' with 'icon_type'.

            Action must exist in self._action_per_id

            Args:
                host_name (str)
                icon_type (IconType)
        """
        action = self._action_per_id.get(host_name)
        if not action:
            raise ValueError("Unknown host {}".format(host_name))

        icon = None
        if icon_type == IconType.IDLE:
            icon = ITrayService.get_icon_idle()
        elif icon_type == IconType.RUNNING:
            icon = ITrayService.get_icon_running()
        elif icon_type == IconType.FAILED:
            icon = ITrayService.get_icon_failed()
        else:
            log.info("Unknown icon type {} for {}".format(icon_type,
                                                          host_name))
        action.setIcon(icon)

    def show_widget(self, host_name):
        """Shows prepared widget for 'host_name'.

            Dialog get initialized when 'host_name' is connecting.
        """
        self._tray_manager.execute_in_main_thread(
            self._show_widget, host_name
        )

    def _show_widget(self, host_name):
        widget = self._window_per_id[host_name]
        widget.show()
        widget.raise_()
        widget.activateWindow()

    async def websocket_handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        widget = None
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    host_name, action, text = self._parse_message(msg)

                    if action == HostMsgAction.CONNECTING:
                        self._action_per_id[host_name] = None
                        # must be sent to main thread, or action wont trigger
                        self._tray_manager.execute_in_main_thread(
                            self._host_is_connecting, host_name, text
                        )
                    elif action == HostMsgAction.CLOSE:
                        # clean close
                        self._close(host_name)
                        await ws.close()
                    elif action == HostMsgAction.INITIALIZED:
                        self._tray_manager.execute_in_main_thread(
                            # must be queued as _host_is_connecting might not
                            # be triggered/finished yet
                            self._set_host_icon, host_name, IconType.RUNNING
                        )
                    elif action == HostMsgAction.ADD:
                        self._tray_manager.execute_in_main_thread(
                            self._add_text, host_name, text
                        )
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    print('ws connection closed with exception %s' %
                          ws.exception())
                    host_name, _, _ = self._parse_message(msg)
                    self._set_host_icon(host_name, IconType.FAILED)
        except CancelledError:  # recoverable
            pass
        except Exception as exc:
            log.warning("Exception during communication", exc_info=True)
            if widget:
                error_msg = str(exc)
                widget.append_text(error_msg)

        return ws

    def _add_text(self, host_name, text):
        widget = self._window_per_id[host_name]
        widget.append_text(text)

    def _close(self, host_name):
        """ Clean close - remove from menu, delete widget."""
        services_submenu = self._tray_manager.get_services_submenu()
        action = self._action_per_id.pop(host_name)
        services_submenu.removeAction(action)
        widget = self._window_per_id.pop(host_name)
        if widget.isVisible():
            widget.hide()
        widget.deleteLater()

    def _parse_message(self, msg):
        data = json.loads(msg.data)
        action = data.get("action")
        host_name = data["host"]
        value = data.get("text")

        return host_name, action, value
