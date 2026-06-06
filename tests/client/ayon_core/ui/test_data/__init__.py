"""Shared test data for UI visual tests.

Contains sample images (avatars, color bars) used only for
developer previews (__main__ blocks) and visual regression tests.
These are NOT shipped with the production client package.
"""

from pathlib import Path

TEST_DATA_DIR = Path(__file__).parent


def test_data_file_cacher(key: str) -> "Path | str":
    """Resolve a key to a test_data image path. Used as file_cacher callback."""
    for ext in ("jpg", "png"):
        p = TEST_DATA_DIR / f"{key}.{ext}"
        if p.exists():
            return p
    return ""

