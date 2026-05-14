"""Loader-only native crash diagnostics (faulthandler + Qt message handler)."""
from __future__ import annotations

import faulthandler
import os

_installed = False
# faulthandler keeps writing to the passed file; the handle must outlive enable().
_loader_faulthandler_log_fp = None


def _log_dir() -> str:
    base = os.environ.get("AYON_USER_LOG_DIR") or os.path.expanduser("~/.ayon/logs")
    return os.path.normpath(base)


def _qt_message_handler(msg_type, context, message: str) -> None:
    """Append Qt fatal/critical lines to the same log as faulthandler."""
    try:
        path = os.path.join(_log_dir(), "loader_qt_messages.log")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        mt = int(msg_type) if msg_type is not None else -1
        loc = ""
        if context is not None:
            loc = getattr(context, "file", None) or ""
            ln = getattr(context, "line", None)
            if loc and ln is not None:
                loc = f"{loc}:{ln} "
        line = f"qt_msg type={mt} {loc}{message}\n"
        with open(path, "a", encoding="utf-8", errors="replace") as fh:
            fh.write(line)
            fh.flush()
    except OSError:
        pass


def install_loader_native_crash_diagnostics() -> None:
    """Enable once per process when LoaderWindow is constructed.

    - faulthandler → ``~/.ayon/logs/loader_faulthandler.log`` (C stack on fatal signals).
    - Qt message handler → ``~/.ayon/logs/loader_qt_messages.log`` (fatals/criticals).
    - ``QT_FATAL_WARNINGS`` is not set here; user may export it for stricter repro.
    """
    global _installed, _loader_faulthandler_log_fp
    if _installed:
        return
    _installed = True

    log_dir = _log_dir()
    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError:
        return

    fh_path = os.path.join(log_dir, "loader_faulthandler.log")
    try:
        fh = open(fh_path, "a", encoding="utf-8", errors="replace")
    except OSError:
        fh = None
    if fh is not None:
        try:
            faulthandler.enable(file=fh, all_threads=True)
            _loader_faulthandler_log_fp = fh
        except Exception:
            try:
                fh.close()
            except OSError:
                pass

    try:
        from qtpy import QtCore

        handler = getattr(QtCore, "qInstallMessageHandler", None)
        if callable(handler):
            handler(_qt_message_handler)
    except Exception:
        pass


def qt_cpp_object_alive(obj: object) -> bool:
    """True if ``obj`` still wraps a live Qt C++ object (for post-drag cleanup)."""
    if obj is None:
        return False
    for mod_name in ("shiboken6", "shiboken2"):
        try:
            mod = __import__(mod_name, fromlist=["isValid"])
            is_valid = getattr(mod, "isValid", None)
            if callable(is_valid):
                return bool(is_valid(obj))
        except Exception:
            continue
    try:
        from qtpy import QT_BINDING
    except Exception:
        return True
    if QT_BINDING == "pyqt6":
        try:
            from PyQt6 import sip as _sip  # type: ignore[attr-defined]

            return not _sip.isdeleted(obj)
        except Exception:
            pass
    if QT_BINDING in ("pyqt5", "pyqt6"):
        try:
            import sip as _sip  # type: ignore

            return not _sip.isdeleted(obj)
        except Exception:
            pass
    return True
