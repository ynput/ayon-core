"""Helpers shared by the widgets of the tool."""

from __future__ import annotations

from ayon_core.ui.style_types import get_ayon_style

# AYON style palette tokens used by the tool
PRIMARY_COLOR = "--md-sys-color-primary-dark"
ON_PRIMARY_COLOR = "--md-sys-color-on-primary-dark"
ON_SURFACE_COLOR = "--md-sys-color-on-surface-dark"
OUTLINE_COLOR = "--md-sys-color-outline-dark"
PANEL_COLOR = "--md-sys-color-background-dark"
INPUT_COLOR = "--md-sys-color-surface-container-low-dark"
DIVIDER_COLOR = "--md-sys-color-surface-container-high-dark"
HIGHEST_SURFACE_COLOR = "--md-sys-color-surface-container-highest-dark"

_FALLBACK_COLORS = {
    PRIMARY_COLOR: "#8fceff",
    ON_PRIMARY_COLOR: "#00344f",
    ON_SURFACE_COLOR: "#f4f5f5",
    OUTLINE_COLOR: "#8b9198",
    PANEL_COLOR: "#252a31",
    INPUT_COLOR: "#1c2026",
    DIVIDER_COLOR: "#353b46",
    HIGHEST_SURFACE_COLOR: "#424a57",
}


def get_palette_color(token: str) -> str:
    """Color of the AYON style palette.

    Args:
        token (str): Palette token, e.g. '--md-sys-color-primary-dark'.

    Returns:
        str: Color as html hex string.

    """
    color = get_ayon_style().model.palette().get(token)
    if color:
        return color
    return _FALLBACK_COLORS.get(token, "#ffffff")
