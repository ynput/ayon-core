from __future__ import annotations

from qtpy import QtWidgets
from qtpy.QtGui import QColor
from qtpy.QtCore import Qt

from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.label import AYLabel
from ayon_core.ui.preview.utils import Style, preview_widget


def build_label_widget() -> QtWidgets.QWidget:
    w = AYContainer(
        layout=AYContainer.Layout.VBox,
        variant=AYContainer.Variants.High,
        margin=16,
        layout_margin=16,
        layout_spacing=16,
    )
    for enabled in (True, False):
        row = AYContainer(
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.High,
            layout_spacing=16,
        )
        row.add_widget(
            QtWidgets.QLabel("Enabled:" if enabled else "Disabled:"),
            stretch=0,
        )
        l1 = AYLabel("Text Only", tool_tip="Text only", copy_text=True)
        l2 = AYLabel(
            icon="indeterminate_question_box", tool_tip="Icon only"
        )
        l3 = AYLabel(
            "Approved",
            icon="check_circle",
            icon_color="#88ff88",
            tool_tip="Text & icon with custom color",
        )
        # print(f"i+t default: {json.dumps(l3._style_data, indent=4)}")
        l4 = AYLabel(
            "Text & Icon",
            icon="favorite",
            tool_tip="Text & icon with default color and 6px margin",
            rel_text_size=4,
            copy_text=True,
        )
        l4.setMargin(6)
        l5 = AYLabel(
            "Badge",
            icon_color="#cd8de2",
            variant=AYLabel.Variants.Badge,
            tool_tip="badge variant",
        )
        # print(f"badge: {json.dumps(l5._style_data, indent=4)}")
        l6 = AYLabel(
            "Badge",
            icon_color="#cd8de2",
            variant=AYLabel.Variants.Badge,
            tool_tip="badge variant with smaller text",
            rel_text_size=-2,
        )
        l7 = AYLabel(
            "bad badge",
            icon_color="",
            variant=AYLabel.Variants.Badge,
            tool_tip="Badly configured badge",
        )
        row.add_widget(l1, stretch=0)
        row.add_widget(l2, stretch=0)
        row.add_widget(l3, stretch=0)
        row.add_widget(l4, stretch=0)
        row.add_widget(l5, stretch=0)
        row.add_widget(l6, stretch=0)
        row.add_widget(l7, stretch=0)

        for i in range(0, 6):
            v = i * 51
            c = QColor(v, v, v, 255)
            pc = i * 20
            badge = AYLabel(
                f"{pc}% grey",
                icon_color=c.name(),
                variant=AYLabel.Variants.Badge,
                tool_tip=f"{pc}% grey badge with text color adaptation",
                contrast_color=c,
                rel_text_size=-3,
            )
            row.add_widget(badge, stretch=0)

        l8 = AYLabel("colored text", text_color="#55aef7")
        row.add_widget(l8, stretch=0)

        l10 = AYLabel(
            "Modeling",
            icon="3d",
            icon_size=16,
            variant=AYLabel.Variants.Entity_Label,
        )
        # print(f"Entity_Label: {json.dumps(l10._style_data, indent=4)}")
        row.add_widget(l10, stretch=0)
        l9 = AYLabel(
            "PRG",
            icon="play_circle",
            icon_color="#f7a355",
            icon_size=16,
            variant=AYLabel.Variants.Entity_Label_Filled,
        )
        # print(
        #     "Entity_Label_Filled: "
        #     f"{json.dumps(l9._style_data, indent=4)}"
        # )
        row.add_widget(l9, stretch=0)
        row.addStretch()

        row.setEnabled(enabled)
        w.add_widget(row)

    # Font sizes and styles
    row_font = AYContainer(
        layout=AYContainer.Layout.HBox,
        variant=AYContainer.Variants.High,
        layout_spacing=16,
    )
    row_font.layout().setAlignment(Qt.AlignmentFlag.AlignLeft)
    row_font.add_widget(AYLabel("Default font"), stretch=0)
    row_font.add_widget(AYLabel("Default font bold", bold=True), stretch=0)
    row_font.add_widget(AYLabel("Default font dim", dim=True), stretch=0)
    row_font.add_widget(
        AYLabel("Default font +2", rel_text_size=2), stretch=0
    )
    row_font.add_widget(
        AYLabel("Default font +4", rel_text_size=4), stretch=0
    )

    w.add_widget(row_font)

    return w


if __name__ == "__main__":
    preview_widget(
        build_label_widget,
        style=Style.AYONStyleOverCSS
    )
