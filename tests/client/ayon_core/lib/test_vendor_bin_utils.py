"""Tests for ayon_core.lib.vendor_bin_utils."""
from __future__ import annotations

import os
import platform
import stat
import tempfile
import unittest
from unittest import mock

from ayon_core.lib import vendor_bin_utils


class FindExecutableWithDirectory(unittest.TestCase):
    """Executable path with directory is not looked up in PATH."""

    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.exe_dir = os.path.join(tmpdir.name, "app")
        self.path_dir = os.path.join(tmpdir.name, "bin")
        os.makedirs(self.exe_dir)
        os.makedirs(self.path_dir)
        self._create_executable(os.path.join(self.path_dir, "tool"))
        patcher = mock.patch.dict(os.environ, {"PATH": self.path_dir})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _create_executable(self, filepath):
        with open(filepath, "w"):
            pass
        os.chmod(filepath, os.stat(filepath).st_mode | stat.S_IXUSR)

    def test_missing_executable_does_not_list_path(self):
        with mock.patch.object(
            vendor_bin_utils.os, "listdir", wraps=os.listdir
        ) as listdir:
            result = vendor_bin_utils.find_executable(
                os.path.join(self.exe_dir, "tool")
            )
        self.assertIsNone(result)
        listdir.assert_called_once_with(self.exe_dir)

    def test_finds_executable_without_extension(self):
        ext = ".exe" if platform.system().lower() == "windows" else ".sh"
        filepath = os.path.join(self.exe_dir, f"tool{ext}")
        self._create_executable(filepath)
        result = vendor_bin_utils.find_executable(
            os.path.join(self.exe_dir, "tool")
        )
        self.assertEqual(result, filepath)


class IsOiioSupportedCache(unittest.TestCase):
    """`is_oiio_supported` validates the executable once per process."""

    def setUp(self):
        vendor_bin_utils.is_oiio_supported.cache_clear()
        self.addCleanup(vendor_bin_utils.is_oiio_supported.cache_clear)
        patcher = mock.patch.object(
            vendor_bin_utils,
            "get_oiio_tool_args",
            return_value=["oiiotool"],
        )
        self.get_args = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(
            vendor_bin_utils,
            "_oiio_executable_validation",
            return_value=True,
        )
        self.validation = patcher.start()
        self.addCleanup(patcher.stop)

    def test_validates_once(self):
        for _ in range(5):
            self.assertTrue(vendor_bin_utils.is_oiio_supported())
        self.validation.assert_called_once_with(["oiiotool"])

    def test_failed_validation_is_cached(self):
        self.validation.return_value = False
        self.assertFalse(vendor_bin_utils.is_oiio_supported())
        self.assertFalse(vendor_bin_utils.is_oiio_supported())
        self.validation.assert_called_once()

    def test_tool_not_found_is_cached(self):
        self.get_args.side_effect = vendor_bin_utils.ToolNotFoundError()
        self.assertFalse(vendor_bin_utils.is_oiio_supported())
        self.assertFalse(vendor_bin_utils.is_oiio_supported())
        self.get_args.assert_called_once()
        self.validation.assert_not_called()

    def test_cache_clear_validates_again(self):
        vendor_bin_utils.is_oiio_supported()
        vendor_bin_utils.is_oiio_supported.cache_clear()
        vendor_bin_utils.is_oiio_supported()
        self.assertEqual(self.validation.call_count, 2)
