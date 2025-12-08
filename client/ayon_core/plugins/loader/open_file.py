import os
import sys
import subprocess
import platform
import collections
import ctypes
from typing import Optional, Any, Callable

from ayon_core.pipeline.load import get_representation_path_with_anatomy
from ayon_core.pipeline.actions import (
    LoaderActionPlugin,
    LoaderActionItem,
    LoaderActionSelection,
    LoaderActionResult,
)


WINDOWS_USER_REG_PATH = (
    r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts"
    r"\{ext}\UserChoice"
)


class _Cache:
    """Cache extensions information.

    Notes:
        The cache is cleared when loader tool is refreshed so it might be
            moved to other place which is not cleared on refresh.

    """
    supported_exts: set[str] = set()
    unsupported_exts: set[str] = set()

    @classmethod
    def is_supported(cls, ext: str) -> bool:
        return ext in cls.supported_exts

    @classmethod
    def already_checked(cls, ext: str) -> bool:
        return (
            ext in cls.supported_exts
            or ext in cls.unsupported_exts
        )

    @classmethod
    def set_ext_support(cls, ext: str, supported: bool) -> None:
        if supported:
            cls.supported_exts.add(ext)
        else:
            cls.unsupported_exts.add(ext)


def _extension_has_assigned_app_windows(ext: str) -> bool:
    import winreg
    progid = None
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            WINDOWS_USER_REG_PATH.format(ext=ext),
        ) as k:
            progid, _ = winreg.QueryValueEx(k, "ProgId")
    except OSError:
        pass

    if progid:
        return True

    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, ext) as k:
            progid = winreg.QueryValueEx(k, None)[0]
    except OSError:
        pass
    return bool(progid)


def _linux_find_desktop_file(desktop: str) -> Optional[str]:
    for dirpath in (
        os.path.expanduser("~/.local/share/applications"),
        "/usr/share/applications",
        "/usr/local/share/applications",
    ):
        path = os.path.join(dirpath, desktop)
        if os.path.isfile(path):
            return path
    return None


def _extension_has_assigned_app_linux(ext: str) -> bool:
    import mimetypes

    mime, _ = mimetypes.guess_type(f"file{ext}")
    if not mime:
        return False

    try:
        # xdg-mime query default <mime>
        desktop = subprocess.check_output(
            ["xdg-mime", "query", "default", mime],
            text=True
        ).strip() or None
    except Exception:
        desktop = None

    if not desktop:
        return False

    desktop_path = _linux_find_desktop_file(desktop)
    if not desktop_path:
        return False
    if desktop_path and os.path.isfile(desktop_path):
        return True
    return False


def _extension_has_assigned_app_macos(ext: str) -> bool:
    # Uses CoreServices/LaunchServices and Uniform Type Identifiers via
    #   ctypes.
    # Steps: ext -> UTI -> default handler bundle id for role 'all'.
    cf = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
    )
    ls = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/CoreServices.framework/Frameworks"
        "/LaunchServices.framework/LaunchServices"
    )

    # CFType/CFString helpers
    CFStringRef = ctypes.c_void_p
    CFAllocatorRef = ctypes.c_void_p
    CFIndex = ctypes.c_long

    kCFStringEncodingUTF8 = 0x08000100

    cf.CFStringCreateWithCString.argtypes = [
        CFAllocatorRef, ctypes.c_char_p, ctypes.c_uint32
    ]
    cf.CFStringCreateWithCString.restype = CFStringRef

    cf.CFStringGetCStringPtr.argtypes = [CFStringRef, ctypes.c_uint32]
    cf.CFStringGetCStringPtr.restype = ctypes.c_char_p

    cf.CFStringGetCString.argtypes = [
        CFStringRef, ctypes.c_char_p, CFIndex, ctypes.c_uint32
    ]
    cf.CFStringGetCString.restype = ctypes.c_bool

    cf.CFRelease.argtypes = [ctypes.c_void_p]
    cf.CFRelease.restype = None

    try:
        UTTypeCreatePreferredIdentifierForTag = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/CoreServices.framework/CoreServices"
        ).UTTypeCreatePreferredIdentifierForTag
    except OSError:
        # Fallback path (older systems)
        UTTypeCreatePreferredIdentifierForTag = (
            ls.UTTypeCreatePreferredIdentifierForTag
        )
    UTTypeCreatePreferredIdentifierForTag.argtypes = [
        CFStringRef, CFStringRef, CFStringRef
    ]
    UTTypeCreatePreferredIdentifierForTag.restype = CFStringRef

    LSRolesMask = ctypes.c_uint
    kLSRolesAll = 0xFFFFFFFF
    ls.LSCopyDefaultRoleHandlerForContentType.argtypes = [
        CFStringRef, LSRolesMask
    ]
    ls.LSCopyDefaultRoleHandlerForContentType.restype = CFStringRef

    def cfstr(py_s: str) -> CFStringRef:
        return cf.CFStringCreateWithCString(
            None, py_s.encode("utf-8"), kCFStringEncodingUTF8
        )

    def to_pystr(cf_s: CFStringRef) -> Optional[str]:
        if not cf_s:
            return None
        # Try fast pointer
        ptr = cf.CFStringGetCStringPtr(cf_s, kCFStringEncodingUTF8)
        if ptr:
            return ctypes.cast(ptr, ctypes.c_char_p).value.decode("utf-8")

        # Fallback buffer
        buf_size = 1024
        buf = ctypes.create_string_buffer(buf_size)
        ok = cf.CFStringGetCString(
            cf_s, buf, buf_size, kCFStringEncodingUTF8
        )
        if ok:
            return buf.value.decode("utf-8")
        return None

    # Convert extension (without dot) to UTI
    tag_class = cfstr("public.filename-extension")
    tag_value = cfstr(ext.lstrip("."))

    uti_ref = UTTypeCreatePreferredIdentifierForTag(
        tag_class, tag_value, None
    )

    # Clean up temporary CFStrings
    for ref in (tag_class, tag_value):
        if ref:
            cf.CFRelease(ref)

    bundle_id = None
    if uti_ref:
        # Get default handler for the UTI
        default_bundle_ref = ls.LSCopyDefaultRoleHandlerForContentType(
            uti_ref, kLSRolesAll
        )
        bundle_id = to_pystr(default_bundle_ref)
        if default_bundle_ref:
            cf.CFRelease(default_bundle_ref)
        cf.CFRelease(uti_ref)
    return bundle_id is not None


def _filter_supported_exts(
    extensions: set[str], test_func: Callable
) -> set[str]:
    filtered_exs: set[str] = set()
    for ext in extensions:
        if not _Cache.already_checked(ext):
            _Cache.set_ext_support(ext, test_func(ext))
        if _Cache.is_supported(ext):
            filtered_exs.add(ext)
    return filtered_exs


def filter_supported_exts(extensions: set[str]) -> set[str]:
    if not extensions:
        return set()
    platform_name = platform.system().lower()
    if platform_name == "windows":
        return _filter_supported_exts(
            extensions, _extension_has_assigned_app_windows
        )
    if platform_name == "linux":
        return _filter_supported_exts(
            extensions, _extension_has_assigned_app_linux
        )
    if platform_name == "darwin":
        return _filter_supported_exts(
            extensions, _extension_has_assigned_app_macos
        )
    return set()


def open_file(filepath: str) -> None:
    """Open file with system default executable"""
    if sys.platform.startswith("darwin"):
        subprocess.call(("open", filepath))
    elif os.name == "nt":
        os.startfile(filepath)
    elif os.name == "posix":
        subprocess.call(("xdg-open", filepath))


class OpenFileAction(LoaderActionPlugin):
    """Open Image Sequence or Video with system default"""
    identifier = "core.open-file"

    def get_action_items(
        self, selection: LoaderActionSelection
    ) -> list[LoaderActionItem]:
        repres = []
        if selection.selected_type == "representation":
            repres = selection.entities.get_representations(
                selection.selected_ids
            )

        if selection.selected_type == "version":
            repres = selection.entities.get_versions_representations(
                selection.selected_ids
            )

        if not repres:
            return []

        repres_by_ext = collections.defaultdict(list)
        for repre in repres:
            repre_context = repre.get("context")
            if not repre_context:
                continue
            ext = repre_context.get("ext")
            if not ext:
                path = repre["attrib"].get("path")
                if path:
                    ext = os.path.splitext(path)[1]

            if ext:
                ext = ext.lower()
                if not ext.startswith("."):
                    ext = f".{ext}"
                repres_by_ext[ext.lower()].append(repre)

        if not repres_by_ext:
            return []

        filtered_exts = filter_supported_exts(set(repres_by_ext))

        repre_ids_by_name = collections.defaultdict(set)
        for ext in filtered_exts:
            for repre in repres_by_ext[ext]:
                repre_ids_by_name[repre["name"]].add(repre["id"])

        return [
            LoaderActionItem(
                label=repre_name,
                group_label="Open file",
                order=30,
                data={"representation_ids": list(repre_ids)},
                icon={
                    "type": "material-symbols",
                    "name": "file_open",
                    "color": "#ffffff",
                }
            )
            for repre_name, repre_ids in repre_ids_by_name.items()
        ]

    def execute_action(
        self,
        selection: LoaderActionSelection,
        data: dict[str, Any],
        form_values: dict[str, Any],
    ) -> Optional[LoaderActionResult]:
        path = None
        repre_path = None
        repre_ids = data["representation_ids"]
        for repre in selection.entities.get_representations(repre_ids):
            repre_path = get_representation_path_with_anatomy(
                repre, selection.get_project_anatomy()
            )
            if os.path.exists(repre_path):
                path = repre_path
                break

        if path is None:
            if repre_path is None:
                return LoaderActionResult(
                    "Failed to fill representation path...",
                    success=False,
                )
            return LoaderActionResult(
                "File to open was not found...",
                success=False,
            )

        self.log.info(f"Opening: {path}")

        open_file(path)

        return LoaderActionResult(
            "File was opened...",
            success=True,
        )
