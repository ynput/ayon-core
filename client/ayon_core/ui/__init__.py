"""AYON Core UI package."""

import sys
import os

# Add the vendor directory to sys.path so that we can import vendored where
# needed.
_vendor_path = os.path.join(
    os.path.dirname(__file__), "..", "vendor", "python"
)
if _vendor_path not in sys.path:
    sys.path.insert(0, _vendor_path)


def _get_test_data_dir():
    """
    As we moved all resources
    from `tests/client/ayon_core/ui` to `tests/client/ayon_core/ui/test_data`
    we need to be able to find the test data directory.
    """
    from pathlib import Path

    # Relative to repo root path tests/client/ayon_core/ui/test_data
    repo_root = Path(__file__).resolve().parents[3]
    test_data = (
        repo_root / "tests" / "client" / "ayon_core" / "ui" / "test_data"
    )
    if test_data.is_dir():
        return test_data
    return None
