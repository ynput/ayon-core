"""macOS Dock shim: tray HTTP routes, per-tool ``.app`` launch, host hooks."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from qtpy import QtCore

if TYPE_CHECKING:
    from aiohttp.web import Request, Response

from ayon_core.lib import Logger
from ayon_core.lib.local_settings import get_launcher_local_dir
from ayon_core.pipeline import registered_host
from ayon_core.tools.tool_icon_wrapper.registry import TOOL_IDENTITIES

_LOG = Logger.get_logger("ToolShim")

TRAY_HTTP_PORT_ENV = "AYON_TRAY_HTTP_PORT"
DOCK_SHIM_DISABLE_ENV = "AYON_DOCK_SHIM_DISABLE"
DOCK_API_V1_PREFIX = "/api/dock/v1"
DCC_COMPANION_JSON = "dcc_companion"
DCC_HOST_PID_JSON = "dcc_host_pid"
DCC_COMPANION_CLI_FLAG = "--ayon-shim-dcc-companion"
_DCC_SHIM_DIR = "dcc_dock"

_FALSEY = frozenset({"0", "false", "no", "off"})
_TRUTHY = frozenset({"1", "true", "yes", "on"})

_DOCK_ROUTE_OPEN_OR_FOCUS = f"{DOCK_API_V1_PREFIX}/open_or_focus"
_DOCK_ROUTE_FOCUS = f"{DOCK_API_V1_PREFIX}/focus"
_DOCK_ROUTE_CLOSE_FROM_SHIM = f"{DOCK_API_V1_PREFIX}/close_from_shim"

_DELEGATION_HOSTS = frozenset({"traypublisher"})

HOST_TOOL_NAME_TO_SHIM: dict[str, Optional[str]] = {
    "launcher": "launcher",
    "loader": "loader",
    "libraryloader": "loader",
    "workfiles": "workfiles",
    "publisher": "publisher",
    "sceneinventory": "scene_inventory",
    "publish": None,
    "experimental_tools": None,
}

TOOL_SHIMS: dict[str, dict[str, str]] = {
    k: {
        "display_name": v["display_name"],
        "bundle_id": v["app_id"],
        "icon": v["icon"],
    }
    for k, v in TOOL_IDENTITIES.items()
}

DOCK_TOOL_KEYS = frozenset(TOOL_SHIMS.keys())

_dcc_tray_close_watcher: Optional[QtCore.QFileSystemWatcher] = None

_NATIVE_TASKBAR_EXC = (
    RuntimeError,
    AttributeError,
    OSError,
    SystemError,
    TypeError,
    ValueError,
)


def _env_truthy(name: str, *, default: bool = True) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    if raw in _FALSEY:
        return False
    if raw in _TRUTHY:
        return True
    return default


def _shim_disabled() -> bool:
    return _env_truthy(DOCK_SHIM_DISABLE_ENV, default=False)


def tray_port() -> Optional[int]:
    raw = (os.environ.get(TRAY_HTTP_PORT_ENV) or "").strip()
    if not raw.isdigit():
        return None
    p = int(raw)
    return p if 1 <= p <= 65535 else None


def _normalize_host_tool_token(name: str) -> str:
    key = (name or "").strip().lower().replace("-", "_")
    if key == "sceneinventory":
        return "scene_inventory"
    return key


def _host_tool_widget(helper: object, host_or_dock_tool_name: str) -> Any:
    key = _normalize_host_tool_token(host_or_dock_tool_name)
    if key == "workfiles":
        return getattr(helper, "_workfiles_tool", None)
    if key in ("loader", "libraryloader"):
        return getattr(helper, "_loader_tool", None)
    if key == "publisher":
        return getattr(helper, "_publisher_tool", None)
    if key == "scene_inventory":
        return getattr(helper, "_scene_inventory_tool", None)
    return None


def request_authorized(request: Request) -> bool:
    return True


def unauthorized_json() -> Response:
    from aiohttp.web import json_response

    return json_response(
        {"success": False, "error": "unauthorized"},
        status=401,
    )


def _apps_dir() -> Path:
    root = get_launcher_local_dir("macos_dock_shim_bundles")
    return Path(root) / "Applications"


def _quit_url_path(dcc_host_pid: int, shim_key: str) -> str:
    return os.path.join(
        get_launcher_local_dir(),
        _DCC_SHIM_DIR,
        f"shim_quit_url_host_{int(dcc_host_pid)}_{shim_key}.txt",
    )


def _close_req_path(dcc_host_pid: int) -> str:
    return os.path.join(
        get_launcher_local_dir(),
        _DCC_SHIM_DIR,
        f"tray_close_host_{int(dcc_host_pid)}.req",
    )


def _shim_key(host_tool_name: str) -> Optional[str]:
    if host_tool_name in HOST_TOOL_NAME_TO_SHIM:
        return HOST_TOOL_NAME_TO_SHIM[host_tool_name]
    if host_tool_name in DOCK_TOOL_KEYS:
        return host_tool_name
    return None


def app_path(tool: str) -> Optional[Path]:
    if tool not in TOOL_SHIMS:
        return None
    name = f"{TOOL_SHIMS[tool]['display_name']}.app"
    p = _apps_dir() / name
    return p if p.is_dir() else None


def write_close_request(dcc_host_pid: int, dock_tool_name: str) -> None:
    p = _close_req_path(dcc_host_pid)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
    except OSError as exc:
        _LOG.debug("write_close_request makedirs: %s", exc)
    try:
        with open(p, "w", encoding="utf-8") as f:
            f.write((dock_tool_name or "").strip() + "\n")
    except OSError as exc:
        _LOG.debug("write_close_request: %s", exc)


def _on_dcc_tray_issued_close(helper: object) -> None:
    p = _close_req_path(os.getpid())
    if not os.path.isfile(p):
        return
    try:
        with open(p, encoding="utf-8") as f:
            line = f.read().strip()
    except OSError:
        return
    if not line:
        return
    try:
        with open(p, "w", encoding="utf-8"):
            pass
    except OSError:
        return
    w = _host_tool_widget(helper, line)
    if w is not None:
        QtCore.QTimer.singleShot(0, w.close)


def _ensure_dcc_close_watcher(helper: object) -> None:
    global _dcc_tray_close_watcher
    if _dcc_tray_close_watcher is not None:
        return
    p = _close_req_path(os.getpid())
    d = os.path.dirname(p)
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        return
    try:
        open(p, "a", encoding="utf-8").close()
    except OSError:
        pass
    w = QtCore.QFileSystemWatcher()
    _ = w.addPath(d)
    _ = w.addPath(p)
    w.directoryChanged.connect(
        lambda *a, h=helper: _on_dcc_tray_issued_close(h)
    )
    w.fileChanged.connect(
        lambda *a, h=helper: _on_dcc_tray_issued_close(h)
    )
    _dcc_tray_close_watcher = w


class _LifecycleFilter(QtCore.QObject):
    def __init__(self, on_close: Callable[[], None]) -> None:
        super().__init__(None)
        self._on_close = on_close

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if event.type() == QtCore.QEvent.Close:
            self._on_close()
        return False


def _post_dcc_shim_quit(host_tool_name: str) -> None:
    key = _shim_key(host_tool_name)
    if not key:
        return
    path = _quit_url_path(os.getpid(), key)
    url = ""
    deadline = time.monotonic() + 0.55
    while time.monotonic() < deadline:
        try:
            with open(path, encoding="utf-8") as f:
                url = f.read().strip()
        except OSError:
            url = ""
        if url:
            break
        time.sleep(0.05)
    if url:
        post_shim_quit_async(url)
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


def attach_shim_lifecycle(
    host_tool_name: str,
    widget: object,
    helper: object,
) -> None:
    if sys.platform != "darwin":
        return
    h = registered_host()
    if h is None:
        return
    host_name = (getattr(h, "name", None) or "").strip()
    if not host_name or host_name in _DELEGATION_HOSTS:
        return
    if _shim_disabled():
        return

    if getattr(widget, "_ayon_shim_lifecycle", False):
        once = getattr(widget, "_ayon_shim_close_once", None)
        if once is not None:
            once[0] = False
        return
    setattr(widget, "_ayon_shim_lifecycle", True)
    setattr(widget, "_ayon_shim_close_once", [False])

    def _on_close_once() -> None:
        once = getattr(widget, "_ayon_shim_close_once", None)
        if once is None or once[0]:
            return
        once[0] = True
        _post_dcc_shim_quit(host_tool_name)

    filt = _LifecycleFilter(_on_close_once)
    filt.setParent(widget)
    widget.installEventFilter(filt)
    widget.destroyed.connect(_on_close_once)
    _ensure_dcc_close_watcher(helper)


def on_host_tool_shown(helper: object, host_tool_name: str) -> None:
    if sys.platform != "darwin":
        return
    h = registered_host()
    if h is None:
        return
    host_name = (getattr(h, "name", None) or "").strip()
    if not host_name or host_name in _DELEGATION_HOSTS:
        return
    if not open_dcc_companion(host_tool_name):
        return
    tool_widget = _host_tool_widget(helper, host_tool_name)
    if tool_widget is not None:
        attach_shim_lifecycle(host_tool_name, tool_widget, helper)


def _is_dedicated_tool_process() -> bool:
    from ayon_core.tools.tray.lib import get_tray_file_info

    info = get_tray_file_info() or {}
    tray_pid = int(info.get("pid") or 0)
    return tray_pid != os.getpid()


def darwin_apply_tool_identity(widget: object, tool_name: str) -> None:
    """Set NSApplication Dock icon for dedicated tool processes."""
    if sys.platform != "darwin":
        return
    meta = TOOL_IDENTITIES.get(tool_name)
    if meta is None:
        return
    if not _is_dedicated_tool_process():
        return
    try:
        from ayon_core import AYON_CORE_ROOT
        from Foundation import NSURL
        import AppKit

        icon_path = Path(AYON_CORE_ROOT) / "resources" / "icons" / meta["icon"]
        if not icon_path.is_file():
            return

        img = AppKit.NSImage.alloc().initWithContentsOfURL_(
            NSURL.fileURLWithPath_(str(icon_path))
        )
        if img is None:
            return
        AppKit.NSApplication.sharedApplication().setApplicationIconImage_(img)
    except _NATIVE_TASKBAR_EXC as exc:
        _LOG.debug("darwin NSApplication icon %s: %s", tool_name, exc)


def open_shim(tool: str) -> bool:
    if platform.system() != "Darwin" or _shim_disabled():
        return False
    path = app_path(tool)
    if not path:
        _LOG.info(
            "Dock shim: no bundle for tool=%s under %s",
            tool,
            _apps_dir(),
        )
        return False
    try:
        r = subprocess.run(
            ["open", str(path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        _LOG.debug("open %s: %s", path, exc)
        return False
    if r.returncode != 0:
        _LOG.debug("open %s failed: %s", path, (r.stderr or r.stdout)[:400])
        return False
    return True


def open_shim_for_tool(host_tool_name: str) -> bool:
    key = _shim_key(host_tool_name)
    return open_shim(key) if key else False


def open_dcc_companion(host_tool_name: str) -> bool:
    if platform.system() != "Darwin":
        return False
    if _shim_disabled():
        return False
    key = _shim_key(host_tool_name)
    if not key:
        return False
    path = app_path(key)
    if not path:
        return False
    dcc_pid = os.getpid()
    callback = ""
    try:
        callback = _quit_url_path(dcc_pid, key)
    except OSError:
        pass
    oargs: list[str] = [
        "open",
        str(path),
        "--args",
        DCC_COMPANION_CLI_FLAG,
        f"--ayon-activate-pid={dcc_pid}",
    ]
    if callback:
        oargs.append(f"--ayon-dcc-callback={callback}")
    try:
        r = subprocess.run(oargs, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        _LOG.debug("DCC companion open %s: %s", path, exc)
        return False
    return r.returncode == 0


def darwin_tray_shim_delegation_from_host(tool_name: str) -> bool:
    if sys.platform != "darwin" or _shim_disabled():
        return False
    h = registered_host()
    if h is None:
        return False
    host_name = (getattr(h, "name", None) or "").strip()
    if not host_name or host_name not in _DELEGATION_HOSTS:
        return False
    return bool(open_shim_for_tool(tool_name))


def host_tools_after_show(
    helper: object, tool_name: str, parent: object
) -> None:
    shim_key = HOST_TOOL_NAME_TO_SHIM.get(tool_name)
    if shim_key:
        widget = helper.get_tool_by_name(tool_name, parent)
        if widget is not None:
            darwin_apply_tool_identity(widget, shim_key)
    on_host_tool_shown(helper, tool_name)


def activate_pid(dcc_host_pid: int) -> bool:
    if platform.system() != "Darwin" or dcc_host_pid <= 0:
        return False
    script = (
        'tell application "System Events" to set frontmost of '
        f"first process whose unix id is {int(dcc_host_pid)} to true"
    )
    try:
        r = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError, TimeoutError) as exc:
        _LOG.debug("activate_pid: %s", exc)
        return False
    return r.returncode == 0


def post_shim_quit_async(url: Optional[str]) -> None:
    if not url:
        return

    def _run() -> None:
        try:
            import urllib.error
            import urllib.request

            req = urllib.request.Request(
                url,
                data=b"{}",
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=2.0):
                pass
        except (
            urllib.error.URLError,
            OSError,
            TimeoutError,
            ValueError,
        ) as exc:
            _LOG.debug("shim quit POST failed: %s (%s)", url, exc)

    threading.Thread(target=_run, daemon=True).start()


class ShimCloseFilter(QtCore.QObject):
    def __init__(self, on_close: Callable[[str], None]) -> None:
        super().__init__()
        self._on_close = on_close
        self._tool_by_id: dict[int, str] = {}

    def register_widget(self, widget: QtCore.QObject, tool_name: str) -> None:
        self._tool_by_id[id(widget)] = tool_name

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if event.type() == QtCore.QEvent.Close:
            name = self._tool_by_id.get(id(obj))
            if name:
                self._on_close(name)
        return False


def register_routes(addons_manager: object, tray_manager: object) -> None:
    if platform.system().lower() != "darwin":
        return
    add = addons_manager.add_route
    open_or_focus = tray_manager._web_dock_open_or_focus
    focus = tray_manager._web_dock_focus
    close_from_shim = tray_manager._web_dock_close_from_shim
    add("POST", _DOCK_ROUTE_OPEN_OR_FOCUS, open_or_focus)
    add("POST", _DOCK_ROUTE_FOCUS, focus)
    add("POST", _DOCK_ROUTE_CLOSE_FROM_SHIM, close_from_shim)
