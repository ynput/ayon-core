"""pytest configuration for tool tests.

Tools import Qt and vendored modules (e.g. ``qargparse``) at module
level, so make both importable headless.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

# Must be set before any Qt import.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[4]
VENDOR_ROOT = REPO_ROOT / "client" / "ayon_core" / "vendor" / "python"
if str(VENDOR_ROOT) not in sys.path:
    sys.path.append(str(VENDOR_ROOT))
