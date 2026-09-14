"""Visual regression tests for AYUserImage."""

from __future__ import annotations

from pathlib import Path

from qtpy.QtWidgets import QWidget

from widget_test import WidgetTest
from ayon_core.ui.components.user_image import AYUserImage
from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.label import AYLabel

_RSRC = Path(__file__).parent.parent / "test_data"


class UserImageTest(WidgetTest):
    """Tests AYUserImage with initials, highlight, and outline variants."""

    size = (500, 160)
    tolerance = 0.0

    def build(self) -> QWidget:
        root = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=20,
            layout_spacing=12,
        )

        row1 = AYContainer(
            layout=AYContainer.Layout.HBox,
            layout_margin=0,
            layout_spacing=16,
        )
        row1.add_widget(AYLabel("highlight=False:"))
        row1.add_widget(
            AYUserImage(
                name="jd", full_name="John Doe", size=40, highlight=False
            )
        )
        row1.add_widget(
            AYUserImage(
                name="ab", full_name="Alice Brown", size=40, highlight=False
            )
        )
        row1.add_widget(AYUserImage(name="?", size=32, highlight=False))
        row1.addStretch(1)
        root.add_widget(row1)

        row2 = AYContainer(
            layout=AYContainer.Layout.HBox,
            layout_margin=0,
            layout_spacing=16,
        )
        row2.add_widget(AYLabel("highlight=True:"))
        row2.add_widget(
            AYUserImage(
                name="jd", full_name="John Doe", size=40, highlight=True
            )
        )
        row2.add_widget(
            AYUserImage(
                name="ab", full_name="Alice Brown", size=40, highlight=True
            )
        )
        row2.addStretch(1)
        root.add_widget(row2)

        row3 = AYContainer(
            layout=AYContainer.Layout.HBox,
            layout_margin=0,
            layout_spacing=16,
        )
        row3.add_widget(AYLabel("outline=False:"))
        row3.add_widget(
            AYUserImage(
                name="jd", full_name="John Doe", size=40, outline=False
            )
        )
        row3.add_widget(
            AYUserImage(name="ab", size=40, outline=False, highlight=True)
        )
        row3.addStretch(1)
        root.add_widget(row3)

        return root

    def steps(self):
        return []


class UserImageMainTest(WidgetTest):
    """Replicates the __main__ build() fixture: image avatars, initials, sizes,
    outline/highlight toggles, and the Entity_Card variant side-by-side."""

    # 14 widgets (8×30 + 4×60 + 2×24) + 13 gaps×4 + 2×8 layout margin
    size = (660, 100)
    tolerance = 0.0

    def build(self) -> QWidget:
        w = AYContainer(
            layout=AYContainer.Layout.HBox,
            margin=8,
            layout_margin=8,
            layout_spacing=4,
        )
        # Default size (30), src from file
        w.add_widget(AYUserImage(src=_RSRC / "avatar1.jpg"))
        w.add_widget(AYUserImage(src=_RSRC / "avatar2.jpg", highlight=True))
        w.add_widget(AYUserImage(src=_RSRC / "avatar3.jpg", outline=False))
        # Initials-only variants
        w.add_widget(AYUserImage(full_name="Oliver Cromwell"))
        w.add_widget(AYUserImage(name="Oliver"))
        w.add_widget(AYUserImage(highlight=True))
        w.add_widget(AYUserImage(name="Oliver", outline=False))
        w.add_widget(AYUserImage(name="Oliver", outline=False, highlight=True))
        # Large (size=60)
        w.add_widget(
            AYUserImage(src=_RSRC / "avatar1.jpg", outline=False, size=60)
        )
        w.add_widget(
            AYUserImage(src=_RSRC / "avatar2.jpg", highlight=True, size=60)
        )
        w.add_widget(AYUserImage(full_name="Oliver Cromwell", size=60))
        w.add_widget(AYUserImage(name="Oliver", outline=False, size=60))
        # Entity_Card variant (size=24)
        w.add_widget(
            AYUserImage(
                name="Milan",
                outline=False,
                size=24,
                variant=AYUserImage.Variants.Entity_Card,
            )
        )
        w.add_widget(
            AYUserImage(
                src=_RSRC / "avatar1.jpg",
                name="Milan",
                outline=False,
                size=24,
                variant=AYUserImage.Variants.Entity_Card,
            )
        )
        return w

    def steps(self):
        return []
