"""Publisher-like Overview page for the workfile template builder."""

from __future__ import annotations

from typing import Optional

from qtpy import QtCore, QtWidgets

from ayon_core.ui.components import AYButton, AYContainer, AYLabel


class OverviewPage(AYContainer):
    """Summary of the scene, template and placeholders."""

    create_requested = QtCore.Signal()
    build_requested = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(
            parent,
            layout=AYContainer.Layout.VBox,
            layout_margin=24,
            layout_spacing=8,
        )

        title = AYLabel("Overview", parent=self, rel_text_size=3)
        description = AYLabel(
            "What this template will build and the context it is tested in.",
            parent=self,
            dim=True,
        )
        description.setWordWrap(True)

        summary_widget = QtWidgets.QWidget(self)
        summary_layout = QtWidgets.QGridLayout(summary_widget)
        summary_layout.setContentsMargins(0, 12, 0, 12)
        summary_layout.setHorizontalSpacing(18)
        summary_layout.setVerticalSpacing(8)
        summary_layout.setColumnStretch(1, 1)

        values = {}
        for row, (key, label) in enumerate((
            ("workfile", "Workfile"),
            ("host", "Host"),
            ("context", "Test context"),
            ("template", "Template"),
            ("placeholders", "Placeholders"),
        )):
            name_label = AYLabel(label, parent=summary_widget, dim=True)
            value_label = AYLabel(
                parent=summary_widget,
                elide_mode=QtCore.Qt.ElideMiddle,
                flexible=True,
            )
            summary_layout.addWidget(name_label, row, 0)
            summary_layout.addWidget(value_label, row, 1)
            values[key] = value_label

        actions = AYContainer(
            self,
            layout=AYContainer.Layout.HBox,
            layout_spacing=8,
        )
        create_btn = AYButton(
            "Create placeholder",
            parent=actions,
            variant=AYButton.Variants.Filled,
            icon="add",
        )
        build_btn = AYButton(
            "Open Build",
            parent=actions,
            variant=AYButton.Variants.Surface,
            icon="build",
        )
        actions.add_widget(create_btn)
        actions.add_widget(build_btn)
        actions.addStretch(1)

        self.add_widget(title)
        self.add_widget(description)
        self.add_widget(summary_widget)
        self.add_widget(actions)
        self.addStretch(1)

        create_btn.clicked.connect(self.create_requested)
        build_btn.clicked.connect(self.build_requested)

        self._values = values
        self._create_btn = create_btn

    def set_summary(
        self,
        workfile: str,
        host: str,
        context: str,
        template_path: Optional[str],
        placeholder_count: int,
    ) -> None:
        """Update the values shown on the overview."""
        values = {
            "workfile": workfile or "Unsaved scene",
            "host": host or "Not available",
            "context": context or "Scene context",
            "template": template_path or "No template set in settings",
            "placeholders": (
                "{} placeholder{}".format(
                    placeholder_count,
                    "" if placeholder_count == 1 else "s",
                )
            ),
        }
        for key, text in values.items():
            label = self._values[key]
            label.setText(text)
            label.setToolTip(text)

    def set_create_enabled(self, enabled: bool) -> None:
        """Disable creating when the host has no placeholder plugins."""
        self._create_btn.setEnabled(enabled)
