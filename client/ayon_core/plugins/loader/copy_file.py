import collections
import ctypes
import os
import platform
import shutil
import subprocess
from pathlib import Path

from typing import Optional, Any

from ayon_core.lib.icon_definitions import MaterialSymbolsIcon
from ayon_core.pipeline.load import get_representation_path_with_anatomy
from ayon_core.pipeline.actions import (
    LoaderActionPlugin,
    LoaderActionItem,
    LoaderActionSelection,
    LoaderActionResult,
)


def _windows_copy(path: str, copy_path: bool) -> bool:
    if copy_path and shutil.which("clip.exe"):
        process = subprocess.Popen(
            ["clip.exe"],
            stdin=subprocess.PIPE,
            close_fds=True,
        )
        process.communicate(input=path.encode("utf-8"))
        return True

    from ctypes import wintypes

    GMEM_MOVEABLE = 0x0002
    CF_UNICODETEXT = 13
    CF_HDROP = 15

    if copy_path:
        cf_to_use = CF_UNICODETEXT
    else:
        cf_to_use = CF_HDROP

    class DROPFILES(ctypes.Structure):
        _fields_ = [
            ("pFiles", wintypes.DWORD),
            ("pt_x", wintypes.LONG),
            ("pt_y", wintypes.LONG),
            ("fNC", wintypes.BOOL),
            ("fWide", wintypes.BOOL),
        ]

    text_bytes = (path + "\0").encode("utf-16-le")
    text_size = len(text_bytes)

    file_list_bytes = (path + "\0\0").encode("utf-16-le")
    struct_size = ctypes.sizeof(DROPFILES)
    total_size = struct_size + len(file_list_bytes)

    dropfiles = DROPFILES()
    dropfiles.pFiles = struct_size
    dropfiles.pt_x = 0
    dropfiles.pt_y = 0
    dropfiles.fNC = False
    dropfiles.fWide = True

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.restype = ctypes.c_int
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = ctypes.c_int
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = ctypes.c_int

    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.restype = ctypes.c_int
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.restype = ctypes.c_void_p

    if not user32.OpenClipboard(None):
        return False
    try:
        if not user32.EmptyClipboard():
            return False

        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, total_size)
        if not h_mem:
            return False

        ptr = kernel32.GlobalLock(h_mem)
        if not ptr:
            kernel32.GlobalFree(h_mem)
            return False
        try:
            if copy_path:
                ctypes.memmove(ptr, text_bytes, text_size)
            else:
                ctypes.memmove(ptr, ctypes.byref(dropfiles), struct_size)
                base_ptr = int(ptr)
                ctypes.memmove(
                    base_ptr + struct_size,
                    file_list_bytes,
                    len(file_list_bytes),
                )
        finally:
            kernel32.GlobalUnlock(h_mem)

        if not user32.SetClipboardData(cf_to_use, h_mem):
            kernel32.GlobalFree(h_mem)
            return False

        return True
    finally:
        user32.CloseClipboard()


class CopyFileActionPlugin(LoaderActionPlugin):
    """Copy published file path to clipboard"""
    identifier = "core.copy-action"

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

        output = []
        if not repres:
            return output

        repre_ids_by_name = collections.defaultdict(set)
        for repre in repres:
            repre_ids_by_name[repre["name"]].add(repre["id"])

        for repre_name, repre_ids in repre_ids_by_name.items():
            repre_id = next(iter(repre_ids), None)
            if not repre_id:
                continue
            output.append(
                LoaderActionItem(
                    label=repre_name,
                    order=32,
                    group_label="Copy file path",
                    data={
                        "representation_id": repre_id,
                        "action": "copy-path",
                    },
                    icon=MaterialSymbolsIcon(
                        "content_copy",
                        color="#999999",
                    )
                )
            )
            output.append(
                LoaderActionItem(
                    label=repre_name,
                    order=33,
                    group_label="Copy file",
                    data={
                        "representation_id": repre_id,
                        "action": "copy-file",
                    },
                    icon=MaterialSymbolsIcon(
                        "file_copy",
                        color="#999999",
                    )
                )
            )
        return output

    def execute_action(
        self,
        selection: LoaderActionSelection,
        data: dict,
        form_values: dict[str, Any],
    ) -> Optional[LoaderActionResult]:
        action = data["action"]
        repre_id = data["representation_id"]
        repre = next(iter(selection.entities.get_representations({repre_id})))
        path = get_representation_path_with_anatomy(
            repre, selection.get_project_anatomy()
        )
        if not path:
            return LoaderActionResult(
                "Failed to get file path for representation.",
                success=False,
            )

        self.log.info(f"Added file path to clipboard: {path}")

        if action == "copy-path":
            # Set to Clipboard
            if self._copy_filepath(str(path)):
                return LoaderActionResult(
                    "Path stored to clipboard...",
                    success=True,
                )
            return LoaderActionResult(
                "Failed to store path to clipboard...",
                success=False,
            )

        if action == "copy-file":
            if self._copy_file(str(path)):
                return LoaderActionResult(
                    "File added to clipboard...",
                    success=True,
                )
            return LoaderActionResult(
                "Failed to add file to clipboard...",
                success=False,
            )

        return LoaderActionResult(
            f"Unknown action '{action}'.",
            success=False,
        )

    def _copy_file(self, path: str) -> bool:
        if not path:
            return False

        normalized_path = os.path.normpath(path)
        if not os.path.exists(normalized_path):
            return False

        

        def _macos_copy() -> bool:
            escaped_path = normalized_path.replace('"', '\\"')
            script = f'set the clipboard to (POSIX file "{escaped_path}")'
            result = subprocess.run(
                ["osascript", "-e", script],
                close_fds=True,
                check=False,
            )
            return result.returncode == 0

        def _linux_copy() -> bool:
            file_uri = Path(normalized_path).resolve().as_uri()
            payload = (file_uri + "\n").encode("utf-8")

            if shutil.which("wl-copy"):
                process = subprocess.Popen(
                    ["wl-copy", "--type", "text/uri-list"],
                    stdin=subprocess.PIPE,
                    close_fds=True,
                )
                process.communicate(input=payload)
                return process.returncode == 0

            if shutil.which("xclip"):
                process = subprocess.Popen(
                    ["xclip", "-selection", "clipboard", "-t", "text/uri-list"],
                    stdin=subprocess.PIPE,
                    close_fds=True,
                )
                process.communicate(input=payload)
                return process.returncode == 0

            return False

        platform_name = platform.system().lower()
        if platform_name == "windows":
            return _windows_copy(normalized_path, copy_path=False)
        if platform_name == "darwin":
            return _macos_copy()
        if platform_name == "linux":
            return _linux_copy()
        return False

    def _copy_filepath(self, path: str) -> bool:
        if not path:
            return False

        def _macos_copy() -> bool:
            process = subprocess.Popen(
                "pbcopy",
                env={"LANG": "en_US.UTF-8"},
                stdin=subprocess.PIPE,
            )
            process.communicate(path.encode("utf-8"))
            return True

        def _linux_copy() -> bool:
            args = None
            if shutil.which("xclip"):
                args = ["xclip", "-selection", "clipboard"]

            elif shutil.which("xsel"):
                args = ["xsel", "-b", "-i"]

            elif shutil.which("wl-copy"):
                args = ["wl-copy"]

            elif shutil.which("klipper") and shutil.which("qdbus"):
                subprocess.run(
                    [
                        "qdbus",
                        "org.kde.klipper",
                        "/klipper",
                        "setClipboardContents",
                        path.encode("utf-8"),
                    ],
                    close_fds=True,
                )
                return True

            if args is None:
                return False

            process = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                close_fds=True,
            )
            process.communicate(input=path.encode("utf-8"))
            return True

        platform_name = platform.system().lower()
        if platform_name == "windows":
            return _windows_copy(path, copy_path=True)
        elif platform_name == "darwin":
            return _macos_copy()
        elif platform_name == "linux":
            return _linux_copy()
        return False
