# -*- coding: utf-8 -*-
"""Best-effort repair: main ``AYON.app`` ``Info.plist`` includes ``LSUIlement``.

When the tray runs inside the installed launcher (``sys.executable`` is
``…/AYON X.app/Contents/MacOS/ayon``), this module can add the
``LSUIlement`` key so the main bundle can hide from the Dock (string ``\"1\"``,
matching common manual plist edits), then run ``xattr -cr`` and ad-hoc
``codesign --force --deep -s -`` on the bundle — the same steps studios often
apply after editing an ``Info.plist``.

**Disk mutation:** Writes to the **installed** ``AYON.app``. The install
location must be writable (writes under ``/Applications`` may fail without
appropriate permissions).

**Signing:** Ad-hoc ``codesign`` replaces ynput's distribution signature on
disk until the next reinstall or vendor-signed update. Gatekeeper /
notarization behavior may differ from the shipped app.

**Dock:** macOS reads ``LSUIlement`` only when the process starts. After a
successful plist change, **quit and relaunch AYON once** for Dock behavior to
match.

**Opt-out:** Set ``AYON_SKIP_LSUILEMENT_PATCH`` to ``1``, ``true``, or ``yes``.
"""
from __future__ import annotations

import os
import platform
import plistlib
import subprocess
import sys
from pathlib import Path

from ayon_core.lib import Logger

_PATCH_ENV = "AYON_SKIP_LSUILEMENT_PATCH"
_LS_KEY = "LSUIElement"

_LOG = Logger.get_logger("EnsureMainBundleLSUIElement")


def _truthy_env_skip() -> bool:
    v = (os.environ.get(_PATCH_ENV) or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _truthy_plist_value(value: object) -> bool:
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(value, (int, float)):
        return value != 0
    return False


def _candidate_launcher_executables() -> list[Path]:
    """Paths that might identify ``…/Something.app/Contents/MacOS/<bin>``."""
    raw: list[str] = []
    env_exe = (os.environ.get("AYON_EXECUTABLE") or "").strip()
    if env_exe:
        raw.append(env_exe)
    raw.append(sys.executable)
    seen: set[str] = set()
    out: list[Path] = []
    for s in raw:
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(Path(s).resolve())
    return out


def _bundle_root_from_macos_binary(exe: Path) -> Path | None:
    if exe.parent.name != "MacOS":
        return None
    if exe.parent.parent.name != "Contents":
        return None
    return exe.parent.parent.parent


def _main_bundle_from_executable() -> Path | None:
    for exe in _candidate_launcher_executables():
        bundle = _bundle_root_from_macos_binary(exe)
        if bundle is not None:
            return bundle
    return None


def _run_logged(argv: list[str]) -> bool:
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or "").strip()
        out = (proc.stdout or "").strip()
        msg = err or out or f"exit {proc.returncode}"
        _LOG.warning("command failed %s: %s", argv, msg)
        return False
    return True


def try_patch_main_bundle_lsuielement() -> None:
    """Patch plist / xattr / codesign when needed; never raises."""
    if platform.system() != "Darwin":
        return
    if _truthy_env_skip():
        _LOG.info(
            "%s is set; skipping main-bundle %s plist patch.",
            _PATCH_ENV,
            _LS_KEY,
        )
        return

    bundle = _main_bundle_from_executable()
    if bundle is None:
        _LOG.info(
            "Skipping main-bundle %s patch: not launched from a .app "
            "(tried executables: %s).",
            _LS_KEY,
            [str(p) for p in _candidate_launcher_executables()],
        )
        return

    plist_path = bundle / "Contents" / "Info.plist"
    if not plist_path.is_file():
        _LOG.warning("Missing Info.plist: %s", plist_path)
        return

    try:
        with open(plist_path, "rb") as f:
            data = plistlib.load(f)
    except OSError as exc:
        _LOG.warning("Could not read plist %s: %s", plist_path, exc)
        return

    if not isinstance(data, dict):
        _LOG.warning("Info.plist root is not a dict: %s", plist_path)
        return

    existing = data.get(_LS_KEY)
    if _truthy_plist_value(existing):
        _LOG.debug(
            "%s already set on main bundle (%s); value=%r",
            _LS_KEY,
            plist_path,
            existing,
        )
        return

    data[_LS_KEY] = "1"
    try:
        with open(plist_path, "wb") as f:
            plistlib.dump(data, f)
    except OSError as exc:
        _LOG.warning("Could not write plist %s: %s", plist_path, exc)
        return

    _LOG.info(
        "Wrote %s=1 to main bundle Info.plist %s (bundle %s). "
        "Quit and relaunch AYON once for Dock changes; install dir must be "
        "writable.",
        _LS_KEY,
        plist_path,
        bundle,
    )

    bundle_s = str(bundle)
    _run_logged(["xattr", "-cr", bundle_s])
    _run_logged(["codesign", "--force", "--deep", "-s", "-", bundle_s])
