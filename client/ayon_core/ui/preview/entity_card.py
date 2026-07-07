from __future__ import annotations

from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.entity_card import AYEntityCard
from ayon_core.ui.preview.utils import Style, preview_widget


_USERS = [
    {"name": "jd", "full_name": "John Doe"},
    {"name": "ab", "full_name": "Alice Brown"},
    {"name": "cm", "full_name": "Charlie Moss"},
]

_STATUS = {
    "name": "In Progress",
    "icon": "play_circle",
    "color": "#3498db",
    "short_name": "PRG",
}

_PRIORITY = {
    "label": "Medium",
    "color": "rgb(52, 152, 219)",
    "icon": "check_indeterminate_small",
    "value": "medium",
}


def build_entity_card_preview_widget():
    w = AYContainer(
        layout=AYContainer.Layout.HBox,
        variant=AYContainer.Variants.Low,
        layout_margin=32,
        layout_spacing=16,
    )

    card1 = AYEntityCard(
        header="ep103sq002",
        path=["sequences", "ep103", "shots"],
        project="com",
        title="Lighting",
        title_icon="lightbulb",
        title_color="#ffd700",
        is_playable=True,
        users=_USERS,
        status=_STATUS,
        priority=_PRIORITY,
    )
    w.add_widget(card1)

    card2 = AYEntityCard(
        header="Loading…",
        title="Animation",
        title_icon="run_circle",
        is_loading=True,
    )
    w.add_widget(card2)

    card3 = AYEntityCard(
        header="No image",
        title="Compositing",
        title_icon="layers",
        users=_USERS[:1],
        status=_STATUS,
        version="v003",
    )
    w.add_widget(card3)

    card4 = AYEntityCard(
        header="Active",
        title="Rigging",
        title_icon="account_tree",
        status=_STATUS,
        priority=_PRIORITY,
        is_active=True,
        is_draggable=True,
    )
    w.add_widget(card4)

    return w


if __name__ == "__main__":
    preview_widget(
        build_entity_card_preview_widget,
        style=Style.AYONStyleOverCSS
    )
