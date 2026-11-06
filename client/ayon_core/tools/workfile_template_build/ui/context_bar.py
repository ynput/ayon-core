"""Bar with the opened workfile and the context used to test it."""

from __future__ import annotations

from typing import Optional

from qtpy import QtCore, QtWidgets

from ayon_core.ui.components import AYButton, AYContainer, AYLabel

from ..abstract import BuildContextItem
from .placeholders_widget import RUN_ICON


class ContextBarWidget(AYContainer):
    """Opened workfile, the context to preview and test it in and a test
    build.

    Signals:
        context_change_requested: User wants to choose a different context.
        context_reset_requested: User wants to use the context of the scene.
        test_build_requested: User wants to populate all placeholders.

    """
    context_change_requested = QtCore.Signal()
    context_reset_requested = QtCore.Signal()
    test_build_requested = QtCore.Signal()

    def __init__(
        self,
        margin: int,
        parent: Optional[QtWidgets.QWidget] = None,
    ):
        super().__init__(
            parent,
            layout=AYContainer.Layout.HBox,
            layout_margin=margin,
            layout_spacing=6,
        )

        icon_label = AYLabel(parent=self, icon="layers", icon_size=20)
        workfile_label = AYLabel(
            parent=self, bold=True, elide_mode=QtCore.Qt.ElideMiddle
        )
        host_label = AYLabel(parent=self, dim=True)

        context_label = AYLabel("Preview as", parent=self, dim=True)
        context_btn = AYButton(
            "",
            parent=self,
            variant=AYButton.Variants.Surface,
            icon="folder",
            tooltip=(
                "Placeholders are previewed and test built as if the scene"
                " was opened in this folder and task.\n"
                "Click to choose a different context."
            ),
        )
        reset_btn = AYButton(
            "Reset",
            parent=self,
            variant=AYButton.Variants.Text,
            tooltip="Use the context of the scene again",
        )
        reset_btn.setVisible(False)
        test_build_btn = AYButton(
            "Test build",
            parent=self,
            variant=AYButton.Variants.Surface,
            icon=RUN_ICON,
            tooltip=(
                "Populate all placeholders in this scene for the"
                " \"Preview as\" context"
            ),
        )
        test_build_btn.setEnabled(False)

        self.add_widget(icon_label)
        self.add_widget(workfile_label)
        self.add_widget(host_label)
        self.addStretch(1)
        self.add_widget(context_label)
        self.add_widget(context_btn)
        self.add_widget(reset_btn)
        self.layout().addSpacing(6)
        self.add_widget(test_build_btn)

        context_btn.clicked.connect(self.context_change_requested)
        reset_btn.clicked.connect(self.context_reset_requested)
        test_build_btn.clicked.connect(self.test_build_requested)

        self._workfile_label = workfile_label
        self._host_label = host_label
        self._context_btn = context_btn
        self._reset_btn = reset_btn
        self._test_build_btn = test_build_btn

    def set_workfile(
        self, workfile_name: Optional[str], host_name: str
    ) -> None:
        """Show the opened workfile.

        Args:
            workfile_name (Optional[str]): File name of the workfile. None
                when the scene is not saved.
            host_name (str): Name of the host.

        """
        text = workfile_name or "Unsaved scene"
        self._workfile_label.setText(text)
        self._workfile_label.setToolTip(text)
        self._host_label.setText(host_name)

    def set_build_context(self, context_item: BuildContextItem) -> None:
        """Show the context placeholders are previewed and built in.

        Args:
            context_item (BuildContextItem): The context.

        """
        self._context_btn.setText(context_item.label)
        self._context_btn.set_variant(
            AYButton.Variants.Tonal
            if context_item.is_override
            else AYButton.Variants.Surface
        )
        self._reset_btn.setVisible(context_item.is_override)

    def set_context_enabled(self, enabled: bool) -> None:
        """Allow to choose a different context.

        Args:
            enabled (bool): Context can be changed.

        """
        self._context_btn.setEnabled(enabled)

    def set_test_build_enabled(self, enabled: bool) -> None:
        """Allow to run a test build.

        Args:
            enabled (bool): Test build can be run.

        """
        self._test_build_btn.setEnabled(enabled)
