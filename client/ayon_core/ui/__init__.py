"""AYON Core UI package."""

import importlib.util
import os
import sys

# Vendored Python modules (e.g. ``qtmaterialsymbols``) live in
# ``ayon_core/vendor/python``.  Only insert that directory on
# ``sys.path`` when at least one of the modules we actually need is
# not already importable.  This avoids leaking the vendor directory
# globally when the host application (or a user environment) already
# provides the dependency through a proper install.
_REQUIRED_VENDOR_MODULES = ("qtmaterialsymbols",)


def _ensure_vendor_modules_importable() -> None:
    """Make sure vendored modules are importable.

    Adds ``ayon_core/vendor/python`` to ``sys.path`` only when one of
    the modules listed in :data:`_REQUIRED_VENDOR_MODULES` cannot be
    found through the normal import machinery.
    """
    for name in _REQUIRED_VENDOR_MODULES:
        if importlib.util.find_spec(name) is not None:
            continue
        vendor_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "vendor", "python")
        )
        if vendor_path not in sys.path:
            sys.path.insert(0, vendor_path)
        return


_ensure_vendor_modules_importable()


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
