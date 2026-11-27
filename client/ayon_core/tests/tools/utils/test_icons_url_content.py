"""Tests for downloading url icons content."""

from __future__ import annotations

import sys
import types
from unittest.mock import Mock

if "qargparse" not in sys.modules:
    sys.modules["qargparse"] = types.ModuleType("qargparse")

from ayon_core.tools.utils import lib


def test_failed_download_is_tried_again(monkeypatch):
    url = "https://example.com/icon.png"
    response = Mock()
    response.read.return_value = b"content"
    urlopen = Mock(side_effect=[OSError("Offline"), response])
    monkeypatch.setattr(lib.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(lib._IconsCache, "_content_cache", {})

    assert lib._IconsCache._get_url_content("url", url) is None
    assert lib._IconsCache._get_url_content("url", url) == b"content"
    # Successful download is cached
    assert lib._IconsCache._get_url_content("url", url) == b"content"
    assert urlopen.call_count == 2


def test_prefetch_skips_invalid_icon_definitions(monkeypatch):
    get_url_content = Mock()
    monkeypatch.setattr(lib._IconsCache, "_get_url_content", get_url_content)

    lib.prefetch_qt_icons([
        {"type": "url"},
        {"type": "url", "url": "https://example.com/icon.png"},
    ])

    get_url_content.assert_called_once_with(
        "url", "https://example.com/icon.png"
    )
