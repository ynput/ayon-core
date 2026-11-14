"""Tests for ayon_core.lib.vendor_bin_utils."""
from __future__ import annotations

import unittest
from unittest import mock

from ayon_core.lib import vendor_bin_utils


class IsOiioSupportedCache(unittest.TestCase):
    """`is_oiio_supported` validates the executable once per arguments."""

    def setUp(self):
        vendor_bin_utils._cached_oiio_executable_validation.cache_clear()
        self.addCleanup(
            vendor_bin_utils._cached_oiio_executable_validation.cache_clear
        )
        self.tool_args = ["oiiotool_a"]
        patcher = mock.patch.object(
            vendor_bin_utils,
            "get_oiio_tool_args",
            side_effect=lambda *_args: list(self.tool_args),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(
            vendor_bin_utils,
            "_oiio_executable_validation",
            return_value=True,
        )
        self.validation = patcher.start()
        self.addCleanup(patcher.stop)

    def test_validates_once_for_same_args(self):
        for _ in range(5):
            self.assertTrue(vendor_bin_utils.is_oiio_supported())
        self.validation.assert_called_once_with(["oiiotool_a"])

    def test_validates_again_when_args_change(self):
        vendor_bin_utils.is_oiio_supported()
        self.tool_args = ["oiiotool_b"]
        vendor_bin_utils.is_oiio_supported()
        vendor_bin_utils.is_oiio_supported()
        self.assertEqual(
            self.validation.call_args_list,
            [mock.call(["oiiotool_a"]), mock.call(["oiiotool_b"])],
        )

    def test_failed_validation_is_cached(self):
        self.validation.return_value = False
        self.assertFalse(vendor_bin_utils.is_oiio_supported())
        self.assertFalse(vendor_bin_utils.is_oiio_supported())
        self.validation.assert_called_once()

    def test_tool_not_found(self):
        with mock.patch.object(
            vendor_bin_utils,
            "get_oiio_tool_args",
            side_effect=vendor_bin_utils.ToolNotFoundError(),
        ):
            self.assertFalse(vendor_bin_utils.is_oiio_supported())
        self.validation.assert_not_called()
