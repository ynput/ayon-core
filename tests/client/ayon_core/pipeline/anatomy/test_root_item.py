"""Tests for AnatomyRoot and its find_root_template_from_path logic.

These tests are intentionally isolated from the rest of Anatomy / AYON server
so they can run without any network connection or AYON credentials.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import os
import pytest
from typing import TYPE_CHECKING, Any, Callable
from unittest.mock import patch

from ayon_core.pipeline.anatomy import Anatomy
from ayon_core.pipeline.anatomy.exceptions import RootMissingEnv
from ayon_core.pipeline.anatomy.roots import AnatomyRoot, AnatomyRoots

if TYPE_CHECKING:
    from ayon_api.typing import ProjectDict


@contextmanager
def multi_patch(*patches: list[Callable]):
    with ExitStack() as stack:
        yield [stack.enter_context(_patch) for _patch in patches]


@pytest.fixture
def anatomy_roots() -> AnatomyRoots:
    """AnatomyRoots instance with a test project entity."""
    project_entity: ProjectDict = {
        "name": "Test",
        "code": "test",
        "type": "project",
        "config": {},
        "taskTypes": {},
        "attrib": {},
    }
    patches = [
        patch(
            (
                "ayon_core.pipeline.anatomy.anatomy.Anatomy."
                "_get_studio_roots_overrides"
            ),
            return_value={},
        ),
        patch(
            (
                "ayon_core.pipeline.anatomy.anatomy.Anatomy."
                "_get_site_root_overrides"
            ),
            return_value={},
        )
    ]

    with multi_patch(*patches) as _mp:
        return AnatomyRoots(Anatomy(
            project_name="Test",
            project_entity=project_entity))


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
    project_entity: ProjectDict = {
        "name": "Test",
        "code": "test",
        "type": "project",
        "config": {},
        "taskTypes": {},
        "attrib": {},
    }
    target_platform = platform_override or "linux"

    patches = [
        patch(
            (
                "ayon_core.pipeline.anatomy.anatomy.Anatomy."
                "_get_studio_roots_overrides"
            ),
            return_value={},
        ),
        patch(
            (
                "ayon_core.pipeline.anatomy.anatomy.Anatomy."
                "_get_site_root_overrides"
            ),
            return_value={},
        ),
        patch("platform.system", return_value=target_platform),
    ]

    with multi_patch(*patches) as _:
        parent = AnatomyRoots(Anatomy(
            project_name="Test",
            project_entity=project_entity))
        raw_data = {"windows": windows, "linux": linux, "darwin": darwin}
        target_platform = platform_override or "linux"
        return AnatomyRoot(
            parent=parent, root_raw_data=raw_data, name=name)


@pytest.fixture
def linux_root() -> AnatomyRoot:
    """AnatomyRoot configured for Linux."""
    return make_root_item(linux="/mnt/projects", platform_override="linux")


@pytest.fixture
def windows_root() -> AnatomyRoot:
    """AnatomyRoot configured for Windows."""
    return make_root_item(windows="C:/projects", platform_override="windows")


@pytest.fixture
def darwin_root() -> AnatomyRoot:
    """AnatomyRoot configured for macOS (Darwin)."""
    return make_root_item(
        darwin="/Volumes/projects", platform_override="darwin"
    )


@pytest.fixture
def multi_platform_root() -> AnatomyRoot:
    """AnatomyRoot with all platforms set, current platform Linux."""
    return make_root_item(
        windows="C:/projects",
        linux="/mnt/projects",
        darwin="/Volumes/projects",
        platform_override="linux",
    )


@pytest.fixture
def cross_platform_root() -> AnatomyRoot:
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
def test_value_uses_current_platform(
        platform: str, expected_value: str) -> None:
    """Test if item values are using current platform.

    Args:
        platform (str): Platform to test.
        expected_value (str): Expected value for the platform.

    """
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
def test_clean_value(make_kwargs: dict[str, str], expected_clean: str) -> None:
    item = make_root_item(**make_kwargs)
    assert item.clean_value == expected_clean


def test_full_key_with_name() -> None:
    item = make_root_item(name="publish", platform_override="linux")
    assert item.full_key == "root[publish]"


def test_value_expands_env_var(anatomy_roots: AnatomyRoots) -> None:
    with patch.dict(os.environ, {"MY_ROOT": "/env/root"}, clear=False):
        with patch("platform.system", return_value="linux"):
            item = AnatomyRoot(
                parent=anatomy_roots,
                root_raw_data={"linux": "{MY_ROOT}/projects"},
                name="work",
            )
    assert item.value == "/env/root/projects"


def test_value_expands_user_home(anatomy_roots: AnatomyRoots) -> None:
    fake_home = "/home/testuser"
    expand = lambda p: p.replace("~", fake_home)  # noqa: E731
    with patch("os.path.expanduser", side_effect=expand):
        with patch("platform.system", return_value="linux"):
            item = AnatomyRoot(
                parent=anatomy_roots,
                root_raw_data={"linux": "~/projects"},
                name="work",
            )
    assert item.value == "/home/testuser/projects"


def test_available_platforms_populated(
        multi_platform_root: AnatomyRoot) -> None:
    """Test if plaform are populated correctly."""
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
def test_find_root_template_matches(
        make_kwargs: dict[str, str],
        input_path: str,
        expected_result: str) -> None:
    """Find root template that matched input path."""
    item = make_root_item(**make_kwargs)
    success, result = item.find_root_template_from_path(input_path)
    assert success is True
    assert result == expected_result


def test_find_root_template_cross_platform(
        cross_platform_root: AnatomyRoot) -> None:
    """Windows root entry is tried even when the current platform is Linux."""
    success, result = cross_platform_root.find_root_template_from_path(
        "C:/projects/myproject/file.ma"
    )
    assert success is True


def test_find_root_template_no_match(linux_root: AnatomyRoot) -> None:
    """Test condition when root template doesn't match."""
    path = "/completely/different/path/file.ma"
    success, result = linux_root.find_root_template_from_path(path)
    assert success is False
    assert result == path


def test_expanded_path_matches_unexpanded_root_with_envvar(
        anatomy_roots: AnatomyRoots) -> None:
    """Root stored as ``{MY_ROOT}/projects``, path already expanded."""
    fake_env = {"MY_ROOT": "/mnt"}
    with patch.dict(os.environ, fake_env, clear=False):
        with patch("platform.system", return_value="linux"):
            item = AnatomyRoot(
                parent=anatomy_roots,
                root_raw_data={
                    "linux": "{MY_ROOT}/projects",
                    "windows": "C:/projects",
                },
                name="work",
            )
        success, result = item.find_root_template_from_path(
            "/mnt/projects/myproject/file.ma"
        )
    assert success is True
    assert result == "{root[work]}/myproject/file.ma"


def test_expanded_path_matches_unexpanded_root_with_tilde(
        anatomy_roots: AnatomyRoots) -> None:
    """Root stored as ``~/projects``, path already expanded."""
    fake_home = "/home/user"
    expand = lambda p: p.replace("~", fake_home)  # noqa: E731
    with patch("os.path.expanduser", side_effect=expand):
        with patch("platform.system", return_value="linux"):
            item = AnatomyRoot(
                parent=anatomy_roots,
                root_raw_data={"linux": "~/projects"},
                name="work",
            )
    with patch("os.path.expanduser", side_effect=expand):
        success, result = item.find_root_template_from_path(
            "/home/user/projects/shot/file.ma"
        )
    assert success is True
    assert result == "{root[work]}/shot/file.ma"


@pytest.mark.parametrize("input_path", [
    "~/projects/shot/file.ma",
    "$MY_ROOT/projects/shot/file.ma",
    "{MY_ROOT}/projects/shot/file.ma",
])
def test_unexpanded_input_path_is_not_expanded(
        anatomy_roots: AnatomyRoots, input_path: str) -> None:
    """Input path must be already resolved, it is not expanded."""
    fake_home = "/home/user"
    expand = lambda p: p.replace("~", fake_home)  # noqa: E731
    with patch("os.path.expanduser", side_effect=expand):
        with patch("platform.system", return_value="linux"):
            item = AnatomyRoot(
                parent=anatomy_roots,
                root_raw_data={"linux": "~/projects"},
                name="work",
            )
    with patch("os.path.expanduser", side_effect=expand):
        with patch.dict(os.environ, {"MY_ROOT": fake_home}, clear=False):
            success, result = item.find_root_template_from_path(input_path)
    assert success is False
    assert result == input_path


def test_no_match_with_expansion_returns_false(
        anatomy_roots: AnatomyRoots) -> None:
    fake_env = {"MY_ROOT": "/mnt"}
    with patch.dict(os.environ, fake_env, clear=False):
        with patch("platform.system", return_value="linux"):
            item = AnatomyRoot(
                parent=anatomy_roots,
                root_raw_data={"linux": "{MY_ROOT}/projects"},
                name="work",
            )
    path = "/completely/different/path/file.ma"
    with patch.dict(os.environ, fake_env, clear=False):
        success, result = item.find_root_template_from_path(path)
    assert success is False
    assert result == path


@pytest.mark.parametrize("raw_root", [
    "$MY_ROOT/projects",
    "${MY_ROOT}/projects",
    "%MY_ROOT%/projects",
])
def test_shell_env_syntax_is_rejected(
        anatomy_roots: AnatomyRoots, raw_root: str) -> None:
    """Only '{ENV_KEY}' is supported, shell-like syntax raises."""
    with patch.dict(os.environ, {"MY_ROOT": "/mnt"}, clear=False):
        with patch("platform.system", return_value="linux"):
            with pytest.raises(RootMissingEnv):
                AnatomyRoot(
                    parent=anatomy_roots,
                    root_raw_data={"linux": raw_root},
                    name="work",
                )


def test_windows_admin_share_is_allowed(anatomy_roots: AnatomyRoots) -> None:
    """'$' which is not an env variable (admin share) is kept."""
    with patch("platform.system", return_value="windows"):
        item = AnatomyRoot(
            parent=anatomy_roots,
            root_raw_data={"windows": "//server/c$/projects"},
            name="work",
        )
    assert item.value == "//server/c$/projects"


def test_missing_env_raises(anatomy_roots: AnatomyRoots) -> None:
    env = {k: v for k, v in os.environ.items() if k != "AYON_TEST_MISSING"}
    with patch.dict(os.environ, env, clear=True):
        with patch("platform.system", return_value="linux"):
            with pytest.raises(RootMissingEnv, match="AYON_TEST_MISSING"):
                AnatomyRoot(
                    parent=anatomy_roots,
                    root_raw_data={"linux": "{AYON_TEST_MISSING}/projects"},
                    name="work",
                )


def test_missing_platform_raises(anatomy_roots: AnatomyRoots) -> None:
    with patch("platform.system", return_value="linux"):
        with pytest.raises(RootMissingEnv, match="linux"):
            AnatomyRoot(
                parent=anatomy_roots,
                root_raw_data={"windows": "C:/projects"},
                name="work",
            )


def test_find_root_template_respects_path_boundary(
        linux_root: AnatomyRoot) -> None:
    """Root '/mnt/projects' must not match '/mnt/projects2'."""
    path = "/mnt/projects2/myproject/file.ma"
    success, result = linux_root.find_root_template_from_path(path)
    assert success is False
    assert result == path


def test_other_platform_root_is_not_expanded(
        anatomy_roots: AnatomyRoots) -> None:
    """'~' in root of other platform is not expanded on current machine."""
    fake_home = "/home/user"
    expand = lambda p: p.replace("~", fake_home)  # noqa: E731
    with patch("os.path.expanduser", side_effect=expand):
        with patch("platform.system", return_value="linux"):
            item = AnatomyRoot(
                parent=anatomy_roots,
                root_raw_data={
                    "linux": "/mnt/projects",
                    "darwin": "~/projects",
                },
                name="work",
            )
        success, _ = item.find_root_template_from_path(
            "/home/user/projects/shot/file.ma"
        )
    assert success is False


def test_path_remapper_uses_expanded_current_root(
        anatomy_roots: AnatomyRoots) -> None:
    fake_home = "/home/user"
    expand = lambda p: p.replace("~", fake_home)  # noqa: E731
    with patch("os.path.expanduser", side_effect=expand):
        with patch("platform.system", return_value="linux"):
            item = AnatomyRoot(
                parent=anatomy_roots,
                root_raw_data={
                    "linux": "~/projects",
                    "windows": "C:/projects",
                },
                name="work",
            )
    result = item.path_remapper(
        "C:/projects/shot/file.ma",
        dst_platform="linux",
        src_platform="windows",
    )
    assert result == "/home/user/projects/shot/file.ma"
    result = item.path_remapper(
        "/home/user/projects/shot/file.ma", dst_platform="windows"
    )
    assert result == "C:/projects/shot/file.ma"


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
        cross_platform_root: AnatomyRoot,
        input_path: str,
        dst_platform: str,
        src_platform: str | None,
        expected: str
) -> None:
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
def test_path_remapper_returns_none(
        linux_root: AnatomyRoot,
        input_path: str,
        remap_kwargs: Any) -> None:
    result = linux_root.path_remapper(input_path, **remap_kwargs)
    assert result is None
