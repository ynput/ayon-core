"""Tests for the AYONStyle singleton accessor."""
from __future__ import annotations

from qtpy import shiboken

from ayon_core.ui.style_types import get_ayon_style


def test_ayon_style_is_owned_by_application(qapp):
    """The application, not Python, owns the shared style.

    On exit PySide deletes all objects owned by Python in random order.
    Widgets with a stylesheet keep a raw pointer to their style, so
    deleting the style first crashed Qt when it deleted those widgets.
    """
    style = get_ayon_style()

    assert style.parent() is qapp
    assert not shiboken.ownedByPython(style)
