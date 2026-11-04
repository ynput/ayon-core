import platform
import shlex

import pytest

from ayon_core.lib.execute import _quote_shell_command, run_subprocess

posix_only = pytest.mark.skipif(
    platform.system().lower() == "windows",
    reason="POSIX shell quoting",
)

# (file name, whether the command quotes the path). A path with a space can
# only work when the command quotes it.
CASES = [
    ("testbatch (2)render.exr", True),
    ("video_v001_b&w.mp4", True),
    ("video_v001_b&w.mp4", False),
    ("a;b|c$d>e<f(2).txt", True),
    ("a;b|c$d>e<f(2).txt", False),
]


@posix_only
@pytest.mark.parametrize(("file_name", "quoted"), CASES)
def test_run_subprocess_shell_special_characters(tmp_path, file_name, quoted):
    """File names with special characters reach the program unchanged."""
    path = tmp_path / file_name
    path.write_text("content")

    path_arg = f'"{path}"' if quoted else str(path)
    output = run_subprocess(f"cat {path_arg}", shell=True)

    assert output == "content"


@posix_only
def test_quote_shell_command_keeps_quoted_argument_together():
    command = '/bin/tool -i "/tmp/a (2)/b&w.exr" -y'

    assert shlex.split(_quote_shell_command(command)) == [
        "/bin/tool",
        "-i",
        "/tmp/a (2)/b&w.exr",
        "-y",
    ]


@posix_only
def test_quote_shell_command_keeps_filter_graph_and_apostrophe():
    command = (
        '/bin/ffmpeg -i "/tmp/it\'s (2).%04d.exr" '
        '-filter:v "scale=1920x1080:flags=lanczos,pad=1920:1080:#000000" -y'
    )

    assert shlex.split(_quote_shell_command(command)) == [
        "/bin/ffmpeg",
        "-i",
        "/tmp/it's (2).%04d.exr",
        "-filter:v",
        "scale=1920x1080:flags=lanczos,pad=1920:1080:#000000",
        "-y",
    ]


@posix_only
def test_run_subprocess_list_arguments_are_untouched(tmp_path):
    path = tmp_path / "a (2)&b.txt"
    path.write_text("content")

    assert run_subprocess(["cat", str(path)]) == "content"


def test_quote_shell_command_unbalanced_quote_is_unchanged():
    command = 'tool -i "/tmp/unbalanced'

    assert _quote_shell_command(command) == command
