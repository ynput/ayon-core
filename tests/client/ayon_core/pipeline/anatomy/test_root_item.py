"""Tests for AnatomyRoot and its find_root_template_from_path logic.

These tests are intentionally isolated from the rest of Anatomy / AYON server
so they can run without any network connection or AYON credentials.
"""
from __future__ import annotations

import os
import pytest
from unittest.mock import patch

from ayon_core.pipeline.anatomy.roots import AnatomyRoot


def make_root_item(
    windows: str = "C:/projects",
    linux: str = "/mnt/projects",
    darwin: str = "/Volumes/projects",
    name: str = "work",
    platform_override: str | None = None,
) -> AnatomyRoot:
    """Create a AnatomyRoot, optionally forcing the *current* platform.

    Helper function for testing.

    Args:
        windows (str, optional): Windows path. Defaults to "C:/projects".
        linux (str, optional): Linux path. Defaults to "/mnt/projects".
        darwin (str, optional): macOS path. Defaults to "/Volumes/projects".
        name (str, optional): Name of the root item. Defaults to "work".
        platform_override (str, optional): Platform override. Defaults to None.

    Returns:
        AnatomyRoot: Root Item.

    """
    raw_data = {"windows": windows, "linux": linux, "darwin": darwin}
    target_platform = platform_override or "linux"
    with patch("platform.system", return_value=target_platform):
        return AnatomyRoot(parent=None, root_raw_data=raw_data, name=name)


@pytest.fixture
def linux_root():
    """AnatomyRoot configured for Linux."""
    return make_root_item(linux="/mnt/projects", platform_override="linux")


@pytest.fixture
def windows_root():
    """AnatomyRoot configured for Windows."""
    return make_root_item(windows="C:/projects", platform_override="windows")


@pytest.fixture
def darwin_root():
    """AnatomyRoot configured for macOS (Darwin)."""
    return make_root_item(
        darwin="/Volumes/projects", platform_override="darwin"
    )


@pytest.fixture
def multi_platform_root():
    """AnatomyRoot with all platforms set, current platform Linux."""
    return make_root_item(
        windows="C:/projects",
        linux="/mnt/projects",
        darwin="/Volumes/projects",
        platform_override="linux",
    )


@pytest.fixture
def cross_platform_root():
    """AnatomyRoot with Linux and Windows paths, running on Linux."""
    return make_root_item(
        windows="C:/projects",
        linux="/mnt/projects",
        platform_override="linux",
    )


@pytest.mark.parametrize("platform,expected_value", [
    ("linux", "/mnt/projects"),
    ("windows", "C:/projects"),
    ("darwin", "/Volumes/projects"),
])
def test_value_uses_current_platform(platform, expected_value):
    item = make_root_item(
        windows="C:/projects",
        linux="/mnt/projects",
        darwin="/Volumes/projects",
        platform_override=platform,
    )
    assert item.value == expected_value


@pytest.mark.parametrize("make_kwargs,expected_clean", [
    (
        {"linux": "/mnt/projects/", "platform_override": "linux"},
        "/mnt/projects",
    ),
    (
        {"windows": "C:\\projects\\work", "platform_override": "windows"},
        "C:/projects/work",
    ),
])
def test_clean_value(make_kwargs, expected_clean):
    item = make_root_item(**make_kwargs)
    assert item.clean_value == expected_clean


def test_full_key_with_name():
    item = make_root_item(name="publish", platform_override="linux")
    assert item.full_key == "root[publish]"


def test_value_expands_env_var():
    with patch.dict(os.environ, {"MY_ROOT": "/env/root"}, clear=False):
        with patch("platform.system", return_value="linux"):
            item = AnatomyRoot(
                parent=None,
                root_raw_data={"linux": "$MY_ROOT/projects"},
                name="work",
            )
    assert item.value == "/env/root/projects"


def test_value_expands_user_home():
    fake_home = "/home/testuser"
    expand = lambda p: p.replace("~", fake_home)  # noqa: E731
    with patch("os.path.expanduser", side_effect=expand):
        with patch("platform.system", return_value="linux"):
            item = AnatomyRoot(
                parent=None,
                root_raw_data={"linux": "~/projects"},
                name="work",
            )
    assert item.value == "/home/testuser/projects"


def test_available_platforms_populated(multi_platform_root):
    expected = {"windows", "linux", "darwin"}
    assert expected == multi_platform_root.available_platforms


@pytest.mark.parametrize("make_kwargs,input_path,expected_result", [
    (
        {"linux": "/mnt/projects", "platform_override": "linux"},
        "/mnt/projects/myproject/file.ma",
        "{root[work]}/myproject/file.ma",
    ),
    (
        {"windows": "C:/Projects", "platform_override": "windows"},
        "C:/PROJECTS/myproject/file.ma",   # case-insensitive
        "{root[work]}/myproject/file.ma",
    ),
    (
        {"darwin": "/Volumes/projects", "platform_override": "darwin"},
        "/Volumes/projects/myproject/file.ma",
        "{root[work]}/myproject/file.ma",
    ),
    (
        {"windows": "C:/projects", "platform_override": "windows"},
        "C:\\projects\\myproject\\file.ma",  # backslashes normalised
        "{root[work]}/myproject/file.ma",
    ),
    (
        # trailing slash on stored root
        {"linux": "/mnt/projects/", "platform_override": "linux"},
        "/mnt/projects/myproject/file.ma",
        "{root[work]}/myproject/file.ma",
    ),
    (
        {"linux": "/mnt/projects", "platform_override": "linux"},
        "/mnt/projects",                   # path == root, no subpath
        "{root[work]}",
    ),
])
def test_find_root_template_matches(make_kwargs, input_path, expected_result):
    item = make_root_item(**make_kwargs)
    success, result = item.find_root_template_from_path(input_path)
    assert success is True
    assert result == expected_result


def test_find_root_template_cross_platform(cross_platform_root):
    """Windows root entry is tried even when the current platform is Linux."""
    success, result = cross_platform_root.find_root_template_from_path(
        "C:/projects/myproject/file.ma"
    )
    assert success is True


def test_find_root_template_no_match(linux_root):
    path = "/completely/different/path/file.ma"
    success, result = linux_root.find_root_template_from_path(path)
    assert success is False
    assert result == path


def test_expanded_path_matches_unexpanded_root_with_envvar():
    """Root stored as ``$MY_ROOT/projects``, path already expanded."""
    fake_env = {"MY_ROOT": "/mnt"}
    with patch.dict(os.environ, fake_env, clear=False):
        with patch("platform.system", return_value="linux"):
            item = AnatomyRoot(
                parent=None,
                root_raw_data={
                    "linux": "$MY_ROOT/projects",
                    "windows": "C:/projects",
                },
                name="work",
            )
        success, result = item.find_root_template_from_path(
            "/mnt/projects/myproject/file.ma"
        )
    assert success is True
    assert result == "{root[work]}/myproject/file.ma"


def test_expanded_path_matches_unexpanded_root_with_tilde():
    """Root stored as ``~/projects``, path already expanded."""
    fake_home = "/home/user"
    expand = lambda p: p.replace("~", fake_home)  # noqa: E731
    with patch("os.path.expanduser", side_effect=expand):
        with patch("platform.system", return_value="linux"):
            item = AnatomyRoot(
                parent=None,
                root_raw_data={"linux": "~/projects"},
                name="work",
            )
    with patch("os.path.expanduser", side_effect=expand):
        success, result = item.find_root_template_from_path(
            "/home/user/projects/shot/file.ma"
        )
    assert success is True
    assert result == "{root[work]}/shot/file.ma"


def test_unexpanded_path_matches_expanded_root():
    """Root already expanded, path passed as ``~/projects/...``."""
    fake_home = "/home/user"
    expand = lambda p: p.replace("~", fake_home)  # noqa: E731
    with patch("platform.system", return_value="linux"):
        item = AnatomyRoot(
            parent=None,
            root_raw_data={"linux": "/home/user/projects"},
            name="work",
        )
    with patch("os.path.expanduser", side_effect=expand):
        success, result = item.find_root_template_from_path(
            "~/projects/shot/file.ma"
        )
    assert success is True
    assert result == "{root[work]}/shot/file.ma"


def test_unexpanded_envvar_path_matches_expanded_root():
    """Root already expanded, path contains ``$MY_ROOT``."""
    fake_env = {"MY_ROOT": "/mnt"}
    with patch("platform.system", return_value="linux"):
        item = AnatomyRoot(
            parent=None,
            root_raw_data={"linux": "/mnt/projects"},
            name="work",
        )
    with patch.dict(os.environ, fake_env, clear=False):
        success, result = item.find_root_template_from_path(
            "$MY_ROOT/projects/shot/file.ma"
        )
    assert success is True
    assert result == "{root[work]}/shot/file.ma"


def test_both_sides_need_expanding():
    """Both root and path contain ``~``."""
    fake_home = "/home/user"
    expand = lambda p: p.replace("~", fake_home)  # noqa: E731
    with patch("os.path.expanduser", side_effect=expand):
        with patch("platform.system", return_value="linux"):
            item = AnatomyRoot(
                parent=None,
                root_raw_data={"linux": "~/projects"},
                name="work",
            )
    with patch("os.path.expanduser", side_effect=expand):
        with patch.dict(os.environ, {"MY_ROOT": "/home/user"}, clear=False):
            success, result = item.find_root_template_from_path(
                "~/projects/shot/file.ma"
            )
    assert success is True


def test_no_match_with_expansion_returns_false():
    fake_env = {"MY_ROOT": "/mnt"}
    with patch.dict(os.environ, fake_env, clear=False):
        with patch("platform.system", return_value="linux"):
            item = AnatomyRoot(
                parent=None,
                root_raw_data={"linux": "$MY_ROOT/projects"},
                name="work",
            )
    path = "/completely/different/path/file.ma"
    with patch.dict(os.environ, fake_env, clear=False):
        success, result = item.find_root_template_from_path(path)
    assert success is False
    assert result == path


# ---------------------------------------------------------------------------
# AnatomyRoot.path_remapper
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("input_path,dst_platform,src_platform,expected", [
    (
        "/mnt/projects/myproject/file.ma", "windows", None,
        "C:/projects/myproject/file.ma",
    ),
    (
        "C:/projects/myproject/file.ma", "linux", "windows",
        "/mnt/projects/myproject/file.ma",
    ),
    (
        "/mnt/projects/myproject/file.ma", "linux", None,
        "/mnt/projects/myproject/file.ma",
    ),
])
def test_path_remapper_success(
    cross_platform_root, input_path, dst_platform, src_platform, expected
):
    kwargs = {"dst_platform": dst_platform}
    if src_platform is not None:
        kwargs["src_platform"] = src_platform
    result = cross_platform_root.path_remapper(input_path, **kwargs)
    assert result == expected


@pytest.mark.parametrize("input_path,remap_kwargs", [
    (
        "/mnt/projects/file.ma",
        {"dst_platform": "foo"},   # unknown platform
    ),
    (
        "/completely/different/path/file.ma",
        {},                          # no matching root
    ),
])
def test_path_remapper_returns_none(linux_root, input_path, remap_kwargs):
    result = linux_root.path_remapper(input_path, **remap_kwargs)
    assert result is None
