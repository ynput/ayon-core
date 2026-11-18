"""Import boundaries of the workfile template builder tool package."""
import os
import subprocess
import sys


def test_package_import_does_not_import_qt():
    """The backend package can be imported without Qt."""
    code = (
        "import sys;"
        "import ayon_core.tools.workfile_template_build;"
        "assert 'qtpy' not in sys.modules"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(sys.path)
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_legacy_dialog_import_path_is_kept():
    from ayon_core.tools.workfile_template_build import (
        WorkfileBuildPlaceholderDialog,
    )

    assert WorkfileBuildPlaceholderDialog.__name__ == (
        "WorkfileBuildPlaceholderDialog"
    )
