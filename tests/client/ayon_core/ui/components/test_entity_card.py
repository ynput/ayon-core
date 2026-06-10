"""Visual regression tests for AYEntityCard."""

from __future__ import annotations

from qtpy.QtWidgets import QWidget

from widget_test import WidgetTest
from ayon_core.ui.components.entity_card import AYEntityCard
from ayon_core.ui.components.container import AYContainer


_USERS = [
    {"name": "jd", "full_name": "John Doe"},
    {"name": "ab", "full_name": "Alice Brown"},
    {"name": "cm", "full_name": "Charlie Moss"},
]
_STATUS_IN_PROGRESS = {
    "name": "In Progress",
    "icon": "play_circle",
    "color": "#3498db",
    "short_name": "PRG",
}
_STATUS_BLOCKED = {
    "name": "On hold",
    "icon": "back_hand",
    "color": "#fa6e46",
    "short_name": "HLD",
}
_PRIORITY = {
    "label": "Medium",
    "color": "rgb(52, 152, 219)",
    "icon": "check_indeterminate_small",
    "value": "medium",
}


class EntityCardTest(WidgetTest):
    """Tests AYEntityCard across default, loading, and no-image states."""

    size = (940, 280)
    tolerance = 0.0

    def build(self) -> QWidget:
        root = AYContainer(
            layout=AYContainer.Layout.HBox,
            layout_margin=16,
            layout_spacing=12,
        )

        # 1. Default — all fields populated
        self._card_default = AYEntityCard(
            header="ep103sq002",
            path=["sequences", "ep103", "shots"],
            project="com",
            title="Lighting",
            title_icon="lightbulb",
            title_color="#ffd700",
            is_playable=True,
            users=_USERS,
            status=_STATUS_IN_PROGRESS,
            priority=_PRIORITY,
        )
        root.add_widget(self._card_default)

        # 2. Loading skeleton
        self._card_loading = AYEntityCard(
            header="ep103sq003",
            title="Animation",
            title_icon="run_circle",
            is_loading=True,
        )
        root.add_widget(self._card_loading)

        # 3. No image — thumbnail placeholder icon
        self._card_no_image = AYEntityCard(
            header="ep103sq004",
            path=["sequences", "ep103", "shots"],
            project="com",
            title="Compositing",
            title_icon="layers",
            users=_USERS[:1],
            status=_STATUS_BLOCKED,
            version="v003",
        )
        root.add_widget(self._card_no_image)

        return root

    def set_active(self) -> None:
        self._card_default.is_active = True

    def set_hover(self) -> None:
        self._card_default.is_active = False
        self._card_default.is_hover = True

    def set_error(self) -> None:
        self._card_default.is_hover = False
        self._card_no_image.is_error = True

    def steps(self):
        return [self.set_active, self.set_hover, self.set_error]
