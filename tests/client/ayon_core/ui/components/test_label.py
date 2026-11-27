"""Visual regression tests for AYLabel."""

from __future__ import annotations

from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.label import AYLabel
from qtpy.QtGui import QColor
from qtpy.QtWidgets import QWidget
from widget_test import WidgetTest


class LabelTest(WidgetTest):
    """Tests AYLabel across all variants, dim/bold/icon states."""

    size = (600, 450)
    tolerance = 0.0

    def build(self) -> QWidget:
        self._w = {}

        root = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=20,
            layout_spacing=10,
        )

        # Default variant - plain, dim, bold
        row_default = AYContainer(
            layout=AYContainer.Layout.HBox,
            layout_margin=0,
            layout_spacing=12,
        )
        self._w["default"] = AYLabel("Default text")
        row_default.add_widget(self._w["default"])
        self._w["dim"] = AYLabel("Dim text", dim=True)
        row_default.add_widget(self._w["dim"])
        self._w["bold"] = AYLabel("Bold text", bold=True)
        row_default.add_widget(self._w["bold"])
        self._w["dim_bold"] = AYLabel("Dim bold text", bold=True, dim=True)
        row_default.add_widget(self._w["dim_bold"])
        self._w["larger"] = AYLabel("Larger text (+4)", rel_text_size=4)
        row_default.add_widget(self._w["larger"])
        self._w["larger_bold"] = AYLabel(
            "Larger text bold (+4)", rel_text_size=4, bold=True
        )
        row_default.add_widget(self._w["larger_bold"])
        self._w["smaller"] = AYLabel("Smaller text (-2)", rel_text_size=-2)
        row_default.add_widget(self._w["smaller"])
        row_default.addStretch(1)
        root.add_widget(row_default)

        # With icon
        row_icon = AYContainer(
            layout=AYContainer.Layout.HBox,
            layout_margin=0,
            layout_spacing=12,
        )
        self._w["home_icon"] = AYLabel("", icon="home", icon_size=20)
        row_icon.add_widget(self._w["home_icon"])
        self._w["star_icon"] = AYLabel(
            "", icon="star", icon_size=24, icon_color="#f4c430"
        )
        row_icon.add_widget(self._w["star_icon"])
        self._w["check_icon"] = AYLabel(
            "", icon="check_circle", icon_size=28, icon_color="#00b894"
        )
        row_icon.add_widget(self._w["check_icon"])
        row_icon.addStretch(1)
        root.add_widget(row_icon)

        # All label variants
        kwargs = {
            AYLabel.Variants.Badge: {
                "icon_color": "#27c999",
                "contrast_color": QColor("#27c999"),
            },
            AYLabel.Variants.Pill: {
                "icon_color": "#275ac9",
                "contrast_color": QColor("#275ac9"),
            },
            AYLabel.Variants.Entity_Label: {
                "icon": "star",
                "icon_color": QColor("#eeeeee"),
            },
            AYLabel.Variants.Entity_Label_Filled: {
                "icon": "play_circle",
                "icon_color": "#f7a355",
                "contrast_color": QColor("#f7a355"),
            },
        }

        for variant in AYLabel.Variants:
            row_variant = AYContainer(
                layout=AYContainer.Layout.HBox,
                layout_margin=0,
                layout_spacing=12,
            )
            self._w[variant.name.lower()] = AYLabel(
                f"{variant.name} label",
                variant=variant,
                **kwargs.get(variant, {}),
            )
            row_variant.add_widget(self._w[variant.name.lower()])
            self._w[f"{variant.name.lower()}_dim"] = AYLabel(
                f"{variant.name} dim",
                variant=variant,
                dim=True,
                **kwargs.get(variant, {}),
            )
            row_variant.add_widget(self._w[f"{variant.name.lower()}_dim"])
            self._w[f"{variant.name.lower()}_bold"] = AYLabel(
                f"{variant.name} bold",
                variant=variant,
                bold=True,
                **kwargs.get(variant, {}),
            )
            row_variant.add_widget(self._w[f"{variant.name.lower()}_bold"])
            row_variant.addStretch(1)
            root.add_widget(row_variant)

        # Tag variant with a colored background container to show contrast
        colored_row = AYContainer(
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Low,
            layout_margin=8,
            layout_spacing=8,
        )
        self._w["tag_on_dark"] = AYLabel(
            "Tag on dark", variant=AYLabel.Variants.Tag
        )
        colored_row.add_widget(self._w["tag_on_dark"])
        colored_row.addStretch(1)
        root.add_widget(colored_row)

        return root

    def disable(self) -> None:
        for w in self._w.values():
            w.setEnabled(False)

    def steps(self):
        return [self.disable]
