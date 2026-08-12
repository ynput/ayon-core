import collections
import ctypes
import os
import platform
import shutil
import subprocess

from typing import Optional, Any

from ayon_core.lib.icon_definitions import MaterialSymbolsIcon
from ayon_core.pipeline.load import get_representation_path_with_anatomy
from ayon_core.pipeline.actions import (
    LoaderActionPlugin,
    LoaderActionItem,
    LoaderActionSelection,
    LoaderActionResult,
)


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
        from qtpy import QtWidgets, QtCore

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

        clipboard = QtWidgets.QApplication.clipboard()
        if not clipboard:
            return LoaderActionResult(
                "Failed to copy file path to clipboard.",
                success=False,
            )

        if action == "copy-path":
            # Set to Clipboard
            clipboard.setText(os.path.normpath(path))

            return LoaderActionResult(
                "Path stored to clipboard...",
                success=True,
            )

        # Build mime data for clipboard
        data = QtCore.QMimeData()
        url = QtCore.QUrl.fromLocalFile(path)
        data.setUrls([url])

        # Set to Clipboard
        clipboard.setMimeData(data)

        return LoaderActionResult(
            "File added to clipboard...",
            success=True,
        )

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

        def _windows_copy() -> bool:
            if shutil.which("clip.exe"):
                process = subprocess.Popen(
                    ["clip.exe"],
                    stdin=subprocess.PIPE,
                    close_fds=True,
                )
                process.communicate(input=path.encode("utf-8"))
                return True

            GMEM_MOVEABLE = 0x0002
            CF_UNICODETEXT = 13
            text_bytes = path.encode("utf-8")
            size = len(text_bytes)

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            # Correct signatures (important on 64-bit)
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

                h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
                if not h_mem:
                    return False

                try:
                    ptr = kernel32.GlobalLock(h_mem)
                    if not ptr:
                        return False
                    try:
                        ctypes.memmove(ptr, text_bytes, size)
                    finally:
                        kernel32.GlobalUnlock(h_mem)

                    if not user32.SetClipboardData(CF_UNICODETEXT, h_mem):
                        return False
                finally:
                    kernel32.GlobalFree(h_mem)

                return True
            finally:
                user32.CloseClipboard()

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
            return _windows_copy()
        elif platform_name == "darwin":
            return _macos_copy()
        elif platform_name == "linux":
            return _linux_copy()
        return False
