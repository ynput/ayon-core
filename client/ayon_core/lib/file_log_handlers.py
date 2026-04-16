"""Rotating file logging for ayon_core (no addon dependency)."""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from logging.handlers import RotatingFileHandler

# Match Harmony client/ayon_harmony/logger.py log rotation settings.
LOG_ROTATE_MAX_BYTES = 25 * 1024 * 1024
LOG_RETENTION_DAYS = 62
LOG_ROTATE_BACKUP_DIGITS = 3
LOG_HANDLER_MAX_BYTES = 2**30

AYON_CORE_DEBUG_LOG_BASENAME = "ayon_core_debug.log"
AYON_CORE_DEBUG_LOG_PREFIX = "ayon_core_debug"


def resolve_ayon_core_log_dir() -> str:
    """Same directory rules as Harmony logger.py lines 29–38."""
    ayon_local_sandbox = os.environ.get("AYON_LOCAL_SANDBOX")
    if ayon_local_sandbox:
        log_dir = os.path.expanduser(
            os.path.expandvars(f"{ayon_local_sandbox}/logs")
        ).replace("\\", "/")
    else:
        log_dir = os.path.expanduser("~/.ayon/logs").replace("\\", "/")
    return log_dir


class NumberedRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler with numbered backups before extension."""

    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None
        dname, fname = os.path.split(self.baseFilename)
        base_no_ext, ext = os.path.splitext(fname)
        pad = LOG_ROTATE_BACKUP_DIGITS
        pattern = re.compile(
            r"^" + re.escape(base_no_ext) + r"(\d+)" + re.escape(ext) + r"$"
        )
        numbered = []
        for name in os.listdir(dname):
            m = pattern.match(name)
            if m:
                numbered.append((int(m.group(1)), name))
        numbered.sort(key=lambda x: x[0], reverse=True)
        for num, name in numbered:
            if num >= 10**pad - 1:
                continue
            src = os.path.join(dname, name)
            dst = os.path.join(
                dname, f"{base_no_ext}{str(num + 1).zfill(pad)}{ext}"
            )
            if os.path.exists(dst):
                os.remove(dst)
            os.rename(src, dst)
        current = os.path.join(dname, fname)
        if os.path.exists(current):
            first_rotated = os.path.join(
                dname, f"{base_no_ext}{'1'.zfill(pad)}{ext}"
            )
            if os.path.exists(first_rotated):
                os.remove(first_rotated)
            os.rename(current, first_rotated)
        if not self.delay:
            self.stream = self._open()


def _delete_old_logs(log_dir: str, log_prefix: str) -> None:
    try:
        cutoff = time.time() - (LOG_RETENTION_DAYS * 86400)
        for name in os.listdir(log_dir):
            if name.startswith(log_prefix):
                path = os.path.join(log_dir, name)
                if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                    os.remove(path)
    except Exception:
        pass


def build_ayon_core_debug_file_handler() -> logging.Handler | None:
    """Create file handler for ayon_core debug logs, or None on failure."""
    log_dir = resolve_ayon_core_log_dir()
    try:
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
    except Exception:
        pass

    file_path = os.path.join(log_dir, AYON_CORE_DEBUG_LOG_BASENAME)

    threading.Thread(
        target=_delete_old_logs,
        args=(log_dir, AYON_CORE_DEBUG_LOG_PREFIX),
        daemon=True,
    ).start()

    try:
        file_handler = NumberedRotatingFileHandler(
            file_path,
            maxBytes=LOG_HANDLER_MAX_BYTES,
            backupCount=999,
        )
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)
        file_handler.set_name("AyonCoreFileHandler")
        if os.path.exists(file_path) and os.path.getsize(file_path) >= LOG_ROTATE_MAX_BYTES:
            file_handler.doRollover()
        return file_handler
    except Exception:
        return None
