"""Bar with the opened workfile and the context used to test it."""

from __future__ import annotations

from typing import Optional

from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.tools.utils import get_qt_icon
from ayon_core.ui.components import AYButton, AYContainer, AYLabel

from ..abstract import BuildContextItem
from .placeholders_widget import RUN_ICON


MENU_ARROW_SIZE = 16
MENU_ARROW_GAP = 2
# Space between the arrow and the right edge of the menu button
MENU_ARROW_MARGIN = 6


class _MenuButton(AYButton):
    """Button with an arrow after its label, so it reads as a menu."""

    def sizeHint(self) -> QtCore.QSize:
        size = super().sizeHint()
        return QtCore.QSize(
            size.width() + MENU_ARROW_SIZE + MENU_ARROW_GAP, size.height()
        )

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        super().paintEvent(event)
        color = self._icon_color.name()
        icon = get_qt_icon({
            "type": "material-symbols",
            "name": "expand_more",
            "color": color,
        })
        # The label is drawn from the left, the arrow takes the space
        #   added in 'sizeHint' at the right.
        rect = self.rect()
        arrow_rect = QtCore.QRect(
            rect.right() - MENU_ARROW_MARGIN - MENU_ARROW_SIZE,
            rect.center().y() - (MENU_ARROW_SIZE // 2) + 1,
            MENU_ARROW_SIZE,
            MENU_ARROW_SIZE,
        )
        painter = QtGui.QPainter(self)
        mode = (
            QtGui.QIcon.Mode.Normal
            if self.isEnabled()
            else QtGui.QIcon.Mode.Disabled
        )
        icon.paint(painter, arrow_rect, QtCore.Qt.AlignCenter, mode)
        painter.end()


class ContextBarWidget(AYContainer):
    """Opened workfile, the context to preview and test it in and a test
    build.

    Signals:
        context_change_requested: User wants to choose a different context.
        context_reset_requested: User wants to use the context of the scene.
        test_build_requested: User wants to populate all placeholders.
        open_template_requested: User wants to open the template file.
        build_from_template_requested: User wants to import the template
            into the current scene and populate it.

    """
    context_change_requested = QtCore.Signal()
    context_reset_requested = QtCore.Signal()
    test_build_requested = QtCore.Signal()
    open_template_requested = QtCore.Signal()
    build_from_template_requested = QtCore.Signal()

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
            "Run all",
            parent=self,
            variant=AYButton.Variants.Surface,
            icon=RUN_ICON,
            tooltip=(
                "Populate every placeholder in the open scene for the"
                " \"Preview as\" context.\n"
                "This changes the scene: reopen the template to undo it."
            ),
        )
        test_build_btn.setEnabled(False)
        template_btn = _MenuButton(
            "Template",
            parent=self,
            variant=AYButton.Variants.Surface,
            icon="description",
            tooltip=(
                "Open or build the template set in settings for the"
                " \"Preview as\" context"
            ),
        )

        template_menu = QtWidgets.QMenu(template_btn)
        # Says why the actions are disabled. Shown only when no template
        #   is set, the button stays enabled so the reason can be found.
        missing_action = template_menu.addAction(
            "No template is set in settings for the \"Preview as\""
            " context"
        )
        missing_action.setEnabled(False)
        missing_action.setVisible(False)
        open_action = template_menu.addAction("Open template\u2026")
        open_action.setToolTip(
            "Open the template file. Unsaved changes in the scene are lost."
        )
        build_action = template_menu.addAction("Build from template\u2026")
        build_action.setToolTip(
            "Import the template into the current scene and populate its"
            " placeholders."
        )
        template_menu.setToolTipsVisible(True)

        self.add_widget(icon_label)
        self.add_widget(workfile_label)
        self.add_widget(host_label)
        self.addStretch(1)
        self.add_widget(context_label)
        self.add_widget(context_btn)
        self.add_widget(reset_btn)
        self.layout().addSpacing(6)
        self.add_widget(template_btn)
        self.add_widget(test_build_btn)

        context_btn.clicked.connect(self.context_change_requested)
        reset_btn.clicked.connect(self.context_reset_requested)
        test_build_btn.clicked.connect(self.test_build_requested)
        template_btn.clicked.connect(self._on_template_click)
        open_action.triggered.connect(self.open_template_requested)
        build_action.triggered.connect(self.build_from_template_requested)

        self._workfile_label = workfile_label
        self._host_label = host_label
        self._context_btn = context_btn
        self._reset_btn = reset_btn
        self._test_build_btn = test_build_btn
        self._template_btn = template_btn
        self._template_menu = template_menu
        self._template_missing_action = missing_action
        self._template_actions = (open_action, build_action)

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
        """Allow to run all placeholders.

        Args:
            enabled (bool): All placeholders can be run.

        """
        self._test_build_btn.setEnabled(enabled)

    def set_template_path(self, template_path: Optional[str]) -> None:
        """Show the template set in settings for the build context.

        Args:
            template_path (Optional[str]): Path to the template file. None
                when no template is set for the build context.

        """
        has_template = bool(template_path)
        self._template_missing_action.setVisible(not has_template)
        for action in self._template_actions:
            action.setEnabled(has_template)
        if has_template:
            tooltip = "Template: {}".format(template_path)
        else:
            tooltip = (
                "No template is set in settings for the \"Preview as\""
                " context"
            )
        self._template_btn.setToolTip(tooltip)

    def _on_template_click(self) -> None:
        self._template_menu.exec_(
            self._template_btn.mapToGlobal(
                QtCore.QPoint(0, self._template_btn.height())
            )
        )
        # The button would stay pressed when the menu was closed by click
        #   on the button.
        self._template_btn.setDown(False)
