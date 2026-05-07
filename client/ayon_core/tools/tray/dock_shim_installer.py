"""Build per-tool macOS Dock shim `.app` bundles into the launcher data dir.

Uses vendored ``tools/tray/ui/dock_shim.swift``, PNGs under
``resources/icons/``, and :func:`install_dock_shim_bundles` /
:func:`try_auto_install_dock_shim_bundles`.

Env: ``AYON_DOCK_SHIM_AUTO_INSTALL``, ``AYON_TRAY_HTTP_PORT``
(see ``tool_shim``).
"""

from __future__ import annotations

import os
import platform
import plistlib
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

from ayon_core import AYON_CORE_ROOT
from ayon_core.lib import Logger, is_dev_mode_enabled
from ayon_core.lib.local_settings import get_launcher_local_dir
from ayon_core.tools.tray.lib import _get_tray_info_filepath
from ayon_core.tools.tray.tool_shim import (
    TOOL_SHIMS,
    TRAY_HTTP_PORT_ENV,
    tray_port,
)

_LOG = Logger.get_logger("DockShimInstaller")

_ICONS_DIR = Path(AYON_CORE_ROOT) / "resources" / "icons"


def _vendored_dock_shim_swift_dir() -> Path:
    return Path(AYON_CORE_ROOT) / "tools" / "tray" / "ui"


def _swift_shim_source_in_dir(src_dir: Path) -> Optional[Path]:
    src_dir = src_dir.expanduser()
    for name in ("dock_shim.swift", "main.swift"):
        p = src_dir / name
        if p.is_file():
            return p
    return None


def _resolve_swift_source_dir() -> Optional[Path]:
    vdir = _vendored_dock_shim_swift_dir()
    if _swift_shim_source_in_dir(vdir) is not None:
        return vdir

    raw = (os.environ.get("AYON_DOCK_SHIM_SOURCE_DIR") or "").strip()
    if raw:
        p = Path(raw).expanduser()
        if _swift_shim_source_in_dir(p) is not None:
            return p
    return None


def _auto_install_env_enabled() -> bool:
    e = (os.environ.get("AYON_DOCK_SHIM_AUTO_INSTALL") or "").strip().lower()
    if e in ("0", "false", "no", "off"):
        return False
    if e in ("1", "true", "yes", "on", "force"):
        return True
    return is_dev_mode_enabled()


def _png_to_icns(png: Path, icns_out: Path) -> bool:
    try:
        with tempfile.TemporaryDirectory() as tmp:
            iconset = Path(tmp) / "icon.iconset"
            iconset.mkdir()
            sizes = [
                (16, "icon_16x16.png"),
                (32, "icon_16x16@2x.png"),
                (32, "icon_32x32.png"),
                (64, "icon_32x32@2x.png"),
                (128, "icon_128x128.png"),
                (256, "icon_128x128@2x.png"),
                (256, "icon_256x256.png"),
                (512, "icon_256x256@2x.png"),
                (512, "icon_512x512.png"),
                (1024, "icon_512x512@2x.png"),
            ]
            for size, out_name in sizes:
                o = iconset / out_name
                r = subprocess.run(
                    [
                        "sips",
                        "-z",
                        str(size),
                        str(size),
                        str(png),
                        "--out",
                        str(o),
                    ],
                    capture_output=True,
                    text=True,
                )
                if r.returncode != 0:
                    _LOG.debug("sips: %s", r.stderr or r.stdout)
                    return False
            r2 = subprocess.run(
                [
                    "iconutil",
                    "-c",
                    "icns",
                    str(iconset),
                    "-o",
                    str(icns_out),
                ],
                capture_output=True,
                text=True,
            )
            if r2.returncode != 0:
                _LOG.debug("iconutil: %s", r2.stderr or r2.stdout)
                return False
    except (OSError, subprocess.SubprocessError) as exc:
        _LOG.debug("icns: %s", exc)
        return False
    return True


def _build_swift_binary(out_dir: Path, src_dir: Path) -> Optional[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    exe = out_dir / "ayon_dock_shim"
    swift_src = _swift_shim_source_in_dir(src_dir)
    if swift_src is None:
        _LOG.warning("No dock_shim.swift or main.swift in %s", src_dir)
        return None
    _LOG.debug("Compiling Dock shim: swiftc -> %s (%s)", exe, swift_src)
    r = subprocess.run(
        [
            "swiftc",
            "-parse-as-library",
            "-O",
            "-framework",
            "AppKit",
            "-framework",
            "Foundation",
            str(swift_src),
            "-o",
            str(exe),
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if r.returncode != 0:
        _LOG.warning(
            "swiftc failed (install Xcode CLT; check Swift shim source): %s",
            (r.stderr or r.stdout)[:800],
        )
        return None
    os.chmod(exe, 0o755)
    _LOG.debug("Dock shim binary built: %s", exe)
    return exe


def _codesign_app_adhoc(app_path: Path) -> bool:
    r = subprocess.run(
        [
            "codesign",
            "-s",
            "-",
            "--force",
            "--deep",
            str(app_path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if r.returncode != 0:
        _LOG.debug(
            "codesign (ad-hoc) failed for %s: %s",
            app_path,
            (r.stderr or r.stdout)[:500],
        )
        return False
    return True


def _one_app_bundle(
    out_root: Path,
    binary: Path,
    tool: str,
    metadata: dict[str, str],
    icon_png: Path,
) -> bool:
    display = metadata["display_name"]
    app_path = out_root / f"{display}.app"
    if app_path.is_dir():
        shutil.rmtree(app_path)
    mdir = app_path / "Contents" / "MacOS"
    rdir = app_path / "Contents" / "Resources"
    mdir.mkdir(parents=True, exist_ok=True)
    rdir.mkdir(parents=True, exist_ok=True)
    ex_name = "ayon_dock_shim"
    shutil.copy2(binary, mdir / ex_name)
    (mdir / ex_name).chmod(0o755)
    base_name = "appicon"
    icns = rdir / f"{base_name}.icns"
    if not _png_to_icns(icon_png, icns):
        return False
    lse: dict[str, str] = {"TOOL_NAME": tool}
    fixed = tray_port()
    if fixed is not None:
        lse[TRAY_HTTP_PORT_ENV] = str(fixed)
    else:
        try:
            lse["AYON_TRAY_METADATA_FILE"] = _get_tray_info_filepath()
        except Exception:
            pass
    pl: dict[str, Any] = {
        "CFBundleDevelopmentRegion": "en",
        "CFBundleDisplayName": display,
        "CFBundleExecutable": ex_name,
        "CFBundleIconFile": base_name,
        "CFBundleIdentifier": metadata["bundle_id"],
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": display,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "0.0.0",
        "CFBundleVersion": "1",
        "LSMinimumSystemVersion": "10.15",
        "NSHighResolutionCapable": True,
        "LSEnvironment": lse,
        "NSPrincipalClass": "NSApplication",
    }
    with open(app_path / "Contents" / "Info.plist", "wb") as f:
        plistlib.dump(pl, f)
    if not _codesign_app_adhoc(app_path):
        _LOG.debug(
            "Dock shim .app unsigned: %s (codesign may help)",
            app_path,
        )
    _LOG.debug("Dock shim .app: %s (LSEnvironment=%s)", app_path, lse)
    return True


def install_dock_shim_bundles() -> bool:
    if platform.system() != "Darwin":
        return False
    _LOG.debug("Dock shim install: building .app bundles")
    src = _resolve_swift_source_dir()
    if not src:
        vdir = _vendored_dock_shim_swift_dir()
        _LOG.info(
            "No Swift shim source (expected %s/dock_shim.swift). "
            "Set AYON_DOCK_SHIM_SOURCE_DIR.",
            vdir,
        )
        return False
    _LOG.debug("Dock shim Swift source dir: %s", src)
    work = Path(get_launcher_local_dir("macos_dock_shim_bundles"))
    work.mkdir(parents=True, exist_ok=True)
    bin_dir = work / "_build"
    exe = _build_swift_binary(bin_dir, src)
    if not exe:
        return False
    if not _ICONS_DIR.is_dir():
        _LOG.warning("Missing %s (PNG sources).", _ICONS_DIR)
        return False
    out = work / "Applications"
    out.mkdir(exist_ok=True)
    any_ok = False
    for tool, meta in TOOL_SHIMS.items():
        png = _ICONS_DIR / meta["icon"]
        if not png.is_file():
            _LOG.warning("Missing icon %s for tool %s", png, tool)
            continue
        if _one_app_bundle(out, exe, tool, meta, png):
            any_ok = True
    if any_ok:
        _LOG.info("Dock shim .app bundles: %s", out)
    return any_ok


def try_auto_install_dock_shim_bundles() -> None:
    """If policy allows, build Dock shim .apps (best-effort, never raises)."""
    if platform.system() != "Darwin":
        return
    if not _auto_install_env_enabled():
        return
    _LOG.debug("Dock shim autoinstall: running install")
    try:
        install_dock_shim_bundles()
    except (OSError, subprocess.SubprocessError) as e:
        _LOG.debug("Dock shim install failed: %s", e, exc_info=True)
    except Exception as e:  # noqa: BLE001
        _LOG.debug("Dock shim install error: %s", e, exc_info=True)
