# -*- coding: utf-8 -*-
"""Best-effort repair: main ``AYON.app`` ``Info.plist`` includes ``LSUIElement``.

When the tray runs inside the installed launcher (``sys.executable`` is
``…/AYON X.app/Contents/MacOS/ayon``), this module ensures the main bundle
``Info.plist`` has ``LSUIElement`` set so the launcher can hide from the Dock.
After a successful plist change, ``xattr -cr`` and ad-hoc
``codesign --force --deep -s -`` are run on the bundle so Gatekeeper accepts
the modified bundle on the next launch.

**Disk mutation:** Writes to the **installed** ``AYON.app``. If the install
location is not writable by the current user (typical for ``/Applications``
when AYON was installed with admin rights), this module will prompt the user
once via ``osascript with administrator privileges`` (the standard macOS
auth dialog) and perform the patch as root. If the user cancels, a marker
file is written so subsequent launches do not re-prompt for the same bundle.

**Signing:** Ad-hoc ``codesign`` replaces ynput's distribution signature on
disk until the next reinstall or vendor-signed update. Gatekeeper /
notarization behavior may differ from the shipped app.

**Dock:** macOS reads ``LSUIElement`` only when the process starts. After a
successful plist change, **quit and relaunch AYON once** for Dock behavior to
match.

**Opt-out:**
    * ``AYON_SKIP_LSUILEMENT_PATCH=1`` — disable entirely.
    * ``AYON_LSUILEMENT_NO_PROMPT=1`` — never escalate; only patch when the
      install is already writable by the current user.
    * Delete the marker file under
      ``get_launcher_local_dir("ensure_lsuielement")`` to re-prompt after a
      previous decline.
"""
from __future__ import annotations

import errno
import hashlib
import os
import platform
import plistlib
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from ayon_core.lib import Logger

_PATCH_ENV = "AYON_SKIP_LSUILEMENT_PATCH"
_NO_PROMPT_ENV = "AYON_LSUILEMENT_NO_PROMPT"
_LS_KEY = "LSUIElement"
_STDERR_TAG = "[ayon LSUIElement]"

_LOG = Logger.get_logger("EnsureMainBundleLSUIElement")


def _emit(msg: str) -> None:
    """Log via the addon logger AND stderr so the launcher console always
    shows what the patcher decided, even when ``ayon_core_debug.log`` is
    not wired or the log level filters our messages out.
    """
    _LOG.info(msg)
    print(f"{_STDERR_TAG} {msg}", file=sys.stderr, flush=True)


def _truthy_env(name: str) -> bool:
    v = (os.environ.get(name) or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _truthy_plist_value(value: object) -> bool:
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(value, (int, float)):
        return value != 0
    return False


def _resolve_main_bundle() -> Path | None:
    """Return ``/Applications/AYON <AYON_VERSION>.app``.

    ``AYON_VERSION`` is set by the launcher bootstrap (`ayon-launcher
    start.py: os.environ["AYON_VERSION"] = __version__`) and identifies the
    installed ``.app`` we want to patch — regardless of where ``sys.executable``
    actually resolves (could be a DMG mount, a dev-mounted volume, etc.).

    Falls back to the bundle that contains ``sys.executable`` when
    ``AYON_VERSION`` is unset / the versioned ``.app`` is missing.
    """
    version = (os.environ.get("AYON_VERSION") or "").strip()
    if version:
        versioned = Path(f"/Applications/AYON {version}.app")
        if versioned.is_dir():
            return versioned
        _emit(
            f"AYON_VERSION={version!r} but {versioned} does not exist; "
            "falling back to the running .app."
        )

    exe = Path(sys.executable).resolve()
    if (
        exe.parent.name == "MacOS"
        and exe.parent.parent.name == "Contents"
    ):
        return exe.parent.parent.parent
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


def _decline_marker_path(bundle: Path) -> Path | None:
    """Per-bundle marker so we do not re-prompt after a user decline."""
    try:
        from ayon_core.lib.local_settings import get_launcher_local_dir
    except ImportError:
        return None
    digest = hashlib.sha1(
        str(bundle.resolve()).encode("utf-8", "replace")
    ).hexdigest()[:16]
    return Path(get_launcher_local_dir("ensure_lsuielement")) / (
        f"{digest}.declined"
    )


def _write_decline_marker(bundle: Path, reason: str) -> None:
    marker = _decline_marker_path(bundle)
    if marker is None:
        return
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            f"bundle={bundle}\nreason={reason}\n", encoding="utf-8"
        )
    except OSError as exc:
        _LOG.debug("Could not write decline marker %s: %s", marker, exc)


def _decline_marker_present(bundle: Path) -> bool:
    marker = _decline_marker_path(bundle)
    if marker is None:
        return False
    return marker.is_file()


def _patch_via_osascript(bundle: Path) -> bool:
    """Elevate via the macOS auth dialog and run plutil/xattr/codesign as root.

    Returns True on success, False on user cancel or any failure.
    """
    plist_path = bundle / "Contents" / "Info.plist"
    fd, script_path = tempfile.mkstemp(prefix="ayon_lsui_", suffix=".sh")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write("#!/bin/sh\nset -e\n")
            fh.write(
                "/usr/bin/plutil -replace LSUIElement -bool YES "
                f"{shlex.quote(str(plist_path))}\n"
            )
            fh.write(f"/usr/bin/xattr -cr {shlex.quote(str(bundle))}\n")
            fh.write(
                "/usr/bin/codesign --force --deep --sign - "
                f"{shlex.quote(str(bundle))}\n"
            )
        os.chmod(script_path, 0o755)

        prompt = (
            f"AYON needs administrator access to update {bundle.name} so "
            "it can hide its generic icon from the Dock. This is a "
            "one-time change."
        )
        # AppleScript: build the shell command via "quoted form of" so the
        # script path tolerates spaces; keep the prompt single-line.
        osa = (
            'do shell script "/bin/sh " & quoted form of '
            f'"{script_path}" with prompt "{prompt}" '
            "with administrator privileges"
        )
        proc = subprocess.run(
            ["/usr/bin/osascript", "-e", osa],
            capture_output=True,
            text=True,
        )
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass

    if proc.returncode == 0:
        return True

    err = (proc.stderr or proc.stdout or "").strip()
    # User cancel: osascript exits 1 with "User canceled. (-128)".
    if "-128" in err or "User canceled" in err:
        _LOG.info("User declined admin elevation for %s plist patch.", _LS_KEY)
    else:
        _LOG.warning("Admin %s patch via osascript failed: %s", _LS_KEY, err)
    return False


def try_patch_main_bundle_lsuielement() -> None:
    """Patch plist / xattr / codesign when needed; never raises."""
    if platform.system() != "Darwin":
        return
    if _truthy_env(_PATCH_ENV):
        _emit(f"{_PATCH_ENV} set; skipping {_LS_KEY} patch.")
        return

    bundle = _resolve_main_bundle()
    _emit(
        f"resolving bundle: AYON_VERSION="
        f"{os.environ.get('AYON_VERSION')!r} sys.executable="
        f"{sys.executable!r} -> bundle={bundle}"
    )
    if bundle is None:
        _emit(
            f"skipping {_LS_KEY} patch: could not resolve a target .app "
            f"(AYON_VERSION unset and sys.executable not inside a .app)."
        )
        return

    plist_path = bundle / "Contents" / "Info.plist"
    if not plist_path.is_file():
        _emit(f"missing Info.plist: {plist_path}")
        return

    try:
        with open(plist_path, "rb") as f:
            data = plistlib.load(f)
    except OSError as exc:
        _emit(f"could not read plist {plist_path}: {exc}")
        return

    if not isinstance(data, dict):
        _emit(f"Info.plist root is not a dict: {plist_path}")
        return

    existing = data.get(_LS_KEY)
    if _truthy_plist_value(existing):
        _emit(
            f"{_LS_KEY} already set on {plist_path} (value={existing!r}); "
            "no patch needed."
        )
        return

    data[_LS_KEY] = True
    try:
        with open(plist_path, "wb") as f:
            plistlib.dump(data, f)
    except OSError as exc:
        if exc.errno == errno.EROFS:
            _emit(
                f"{plist_path} is on a read-only filesystem ({exc}); "
                f"skipping {_LS_KEY} patch."
            )
            return
        # EACCES / EPERM (PermissionError is OSError with these errnos):
        # try admin elevation via the macOS auth dialog.
        if exc.errno in (errno.EACCES, errno.EPERM):
            if _truthy_env(_NO_PROMPT_ENV):
                _emit(
                    f"{plist_path} not writable and {_NO_PROMPT_ENV} set; "
                    "skipping admin elevation."
                )
                return
            if _decline_marker_present(bundle):
                _emit(
                    f"skipping {_LS_KEY} admin elevation: prior decline "
                    "recorded (remove marker under ensure_lsuielement/ to "
                    "re-prompt)."
                )
                return
            _emit(
                f"{plist_path} not writable ({exc}); requesting admin "
                f"elevation to patch {_LS_KEY} + ad-hoc resign."
            )
            if _patch_via_osascript(bundle):
                _emit(
                    f"admin {_LS_KEY} patch applied to {bundle}. Quit and "
                    "relaunch AYON for Dock changes to take effect."
                )
            else:
                _write_decline_marker(bundle, "osascript_failed_or_canceled")
            return
        _emit(f"could not write plist {plist_path}: {exc}")
        return

    _emit(
        f"wrote {_LS_KEY}=true to {plist_path} (bundle {bundle}). Quit "
        "and relaunch AYON once for Dock changes."
    )

    bundle_s = str(bundle)
    _run_logged(["xattr", "-cr", bundle_s])
    _run_logged(["codesign", "--force", "--deep", "-s", "-", bundle_s])
