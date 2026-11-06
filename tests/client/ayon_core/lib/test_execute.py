import platform

import pytest

from ayon_core.lib.execute import run_subprocess

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
def test_run_subprocess_shell_command_keeps_quoted_argument_together(
    tmp_path,
):
    path = tmp_path / "it's (2)&b.txt"
    path.write_text("content")

    command = f'python3 -c \'import sys; print(sys.argv[1], end="")\' "{path}"'
    assert run_subprocess(command, shell=True) == str(path)


@posix_only
def test_run_subprocess_list_arguments_are_untouched(tmp_path):
    path = tmp_path / "a (2)&b.txt"
    path.write_text("content")

    assert run_subprocess(["cat", str(path)]) == "content"


@posix_only
def test_run_subprocess_unbalanced_quote_raises():
    with pytest.raises(ValueError):
        run_subprocess('cat "/tmp/unbalanced', shell=True)


@posix_only
def test_run_subprocess_does_not_run_injected_command(tmp_path):
    marker = tmp_path / "injected"
    command = f"cat clip;touch${{IFS}}{marker};#'.mp4"

    with pytest.raises(ValueError):
        run_subprocess(command, shell=True)

    assert not marker.exists()
