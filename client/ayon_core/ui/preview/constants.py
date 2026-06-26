from __future__ import annotations



"""Sample status definitions for prototyping and tests.

Each entry is a :class:`dict` with the following keys:

- ``"text"``       - Full display label shown in
  :attr:`~ayon_core.ui.data_models.MenuSize.Full` mode.
- ``"short_text"`` - Abbreviated label (≤ 3 chars) shown in
  :attr:`~ayon_core.ui.data_models.MenuSize.Short` mode.
- ``"icon"``       - Material Symbol icon name passed to ``get_icon()``.
- ``"color"``      - Hex colour string used as the item foreground.
"""
EXAMPLE_STATUSES = [
    {
        "text": "Not ready",
        "short_text": "NRD",
        "icon": "fiber_new",
        "color": "#434a56",
    },
    {
        "text": "Ready to start",
        "short_text": "RDY",
        "icon": "timer",
        "color": "#bababa",
    },
    {
        "text": "In progress",
        "short_text": "PRG",
        "icon": "play_arrow",
        "color": "#3498db",
    },
    {
        "text": "Pending review",
        "short_text": "RVW",
        "icon": "visibility",
        "color": "#ff9b0a",
    },
    {
        "text": "Approved",
        "short_text": "APP",
        "icon": "task_alt",
        "color": "#00f0b4",
    },
    {
        "text": "On hold",
        "short_text": "HLD",
        "icon": "back_hand",
        "color": "#fa6e46",
    },
    {
        "text": "Omitted",
        "short_text": "OMT",
        "icon": "block",
        "color": "#cb1a1a",
    },
]
