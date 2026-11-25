"""Preview of what a placeholder would do when the template is built."""

from __future__ import annotations

from typing import Optional

from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.pipeline.workfile.workfile_template_builder import (
    PlaceholderPreview,
)
from ayon_core.ui.components import AYContainer, AYLabel, AYTreeView

from .placeholder_item_delegate import COLUMN_PADDING
from .utils import get_warning_color

# Maximum height of the preview entries view
MAX_PREVIEW_HEIGHT = 200


class _HintingFilter(QtCore.QObject):
    """Keep the default font hinting of a widget.

    The AYON style sets its font again whenever the widget is polished,
    so the hinting is set again after each font change.
    """

    @classmethod
    def install(cls, widget: QtWidgets.QWidget) -> None:
        """Use the default hinting for the widget font.

        Args:
            widget (QtWidgets.QWidget): Widget to change.

        """
        hinting_filter = cls(widget)
        widget.installEventFilter(hinting_filter)
        cls._set_hinting(widget)

    @staticmethod
    def _set_hinting(widget: QtWidgets.QWidget) -> None:
        hinting = QtGui.QFont.HintingPreference.PreferDefaultHinting
        font = widget.font()
        if font.hintingPreference() == hinting:
            return
        font = QtGui.QFont(font)
        font.setHintingPreference(hinting)
        widget.setFont(font)

    def eventFilter(self, obj, event):
        if event.type() in (
            QtCore.QEvent.Type.Polish,
            QtCore.QEvent.Type.FontChange,
        ):
            self._set_hinting(obj)
        return False


class PreviewWidget(AYContainer):
    """Shows what a placeholder would do when the template is built."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(
            parent,
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.Low,
            layout_margin=10,
            layout_spacing=6,
        )

        title_widget = AYContainer(
            self,
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.Low,
            layout_spacing=2,
        )
        title_label = AYLabel(
            "Preview",
            parent=title_widget,
            bold=True,
            elide_mode=QtCore.Qt.ElideRight,
        )
        context_label = AYLabel(
            parent=title_widget, dim=True, elide_mode=QtCore.Qt.ElideMiddle
        )
        title_widget.add_widget(title_label)
        title_widget.add_widget(context_label)
        title_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred,
            QtWidgets.QSizePolicy.Maximum,
        )

        warning_label = AYLabel(
            parent=self,
            icon="warning",
            icon_color=get_warning_color(),
            icon_size=16,
        )
        hint_label = AYLabel(parent=self, dim=True, flexible=True)
        hint_label.setWordWrap(True)
        hint_label.setAlignment(
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop
        )

        hint_widget = AYContainer(
            self,
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Low,
            layout_spacing=6,
        )
        hint_widget.add_widget(warning_label)
        hint_widget.add_widget(hint_label, stretch=1)
        hint_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred,
            QtWidgets.QSizePolicy.Maximum,
        )

        items_model = QtGui.QStandardItemModel()
        items_model.setColumnCount(2)

        items_view = AYTreeView(self, variant=AYTreeView.Variants.Low)
        items_view.setModel(items_model)
        items_view.setHeaderHidden(True)
        items_view.setRootIsDecorated(False)
        items_view.setIndentation(0)
        items_view.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection
        )
        items_view.setFocusPolicy(QtCore.Qt.StrongFocus)
        items_view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        items_view.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding,
        )
        header = items_view.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(
            0, QtWidgets.QHeaderView.Stretch
        )
        header.setSectionResizeMode(
            1, QtWidgets.QHeaderView.Fixed
        )

        copy_shortcut = QtWidgets.QShortcut(
            QtGui.QKeySequence.Copy, items_view
        )
        copy_shortcut.activated.connect(self._copy_selected)

        items_view.customContextMenuRequested.connect(
            self._on_items_context_menu
        )

        self.add_widget(title_widget)
        self.layout().addWidget(hint_widget, 0, QtCore.Qt.AlignTop)
        self.add_widget(items_view, stretch=1)
        self.layout().setAlignment(QtCore.Qt.AlignTop)

        self._title_label = title_label
        self._context_label = context_label
        self._warning_label = warning_label
        self._hint_label = hint_label
        self._hint_widget = hint_widget
        self._items_model = items_model
        self._items_view = items_view
        self._copy_shortcut = copy_shortcut
        self._preview: Optional[PlaceholderPreview] = None

    def set_context_label(self, label: str) -> None:
        """Show the context the preview is calculated for.

        Args:
            label (str): Label of the context.

        """
        text = "for {}".format(label) if label else ""
        self._context_label.setText(text)
        self._context_label.setToolTip(text)

    def set_calculating(self) -> None:
        """Show that the preview is being re-calculated."""
        self._title_label.setText("Calculating preview...")
        self._set_hint(None, False)

    def set_preview(self, preview: Optional[PlaceholderPreview]) -> None:
        """Show result of a preview calculation.

        Args:
            preview (Optional[PlaceholderPreview]): Preview to show. Widget
                hides itself when None is passed.

        """
        if preview is None:
            self._preview = None
            self._title_label.setText("Preview")
            self._set_hint(
                "Select a placeholder to see what it would load.",
                False,
            )
            root_item = self._items_model.invisibleRootItem()
            root_item.removeRows(0, root_item.rowCount())
            self._items_view.setVisible(False)
            return

        self._preview = preview
        self._title_label.setText(preview.title or "Preview")
        self._set_hint(preview.hint, preview.is_error)

        root_item = self._items_model.invisibleRootItem()
        root_item.removeRows(0, root_item.rowCount())

        rows = [(item.label, item.detail or "") for item in preview.items]
        if preview.hidden_items_count:
            rows.append(
                ("... and {} more".format(preview.hidden_items_count), "")
            )

        for label, detail in rows:
            label_item = QtGui.QStandardItem(label)
            label_item.setToolTip(label)
            detail_item = QtGui.QStandardItem(detail)
            detail_item.setToolTip(detail)
            for item in (label_item, detail_item):
                item.setEditable(False)
            root_item.appendRow([label_item, detail_item])

        self._items_view.setVisible(bool(preview.items))
        self._items_view.setToolTip(
            "Select rows and use Ctrl+C or the context menu to copy."
        )
        font_metrics = self._items_view.fontMetrics()
        detail_width = max(
            (
                font_metrics.horizontalAdvance(detail)
                for _, detail in rows
                if detail
            ),
            default=0,
        )
        self._items_view.header().resizeSection(
            1, max(60, detail_width + COLUMN_PADDING)
        )
        self._update_items_view_height()

    def _on_items_context_menu(self, point: QtCore.QPoint) -> None:
        menu = QtWidgets.QMenu(self._items_view)
        copy_action = menu.addAction("Copy")
        copy_all_action = menu.addAction("Copy all")
        action = menu.exec_(
            self._items_view.viewport().mapToGlobal(point)
        )
        if action is copy_action:
            self._copy_selected()
        elif action is copy_all_action:
            self._copy_all()

    def _copy_selected(self) -> None:
        selection_model = self._items_view.selectionModel()
        rows = sorted({
            index.row()
            for index in selection_model.selectedIndexes()
        })
        lines = []
        for row in rows:
            text = self._row_text(row)
            if text:
                lines.append(text)
        if lines:
            self._set_clipboard("\n".join(lines))

    def _copy_all(self) -> None:
        if self._preview is None:
            return
        lines = [
            "{} - {}".format(item.label, item.detail or "").rstrip(" -")
            for item in self._preview.items
        ]
        if self._preview.hidden_items_count:
            lines.append(
                "... and {} more".format(
                    self._preview.hidden_items_count
                )
            )
        if lines:
            self._set_clipboard("\n".join(lines))

    def _row_text(self, row: int) -> str:
        label_item = self._items_model.item(row, 0)
        detail_item = self._items_model.item(row, 1)
        if label_item is None:
            return ""
        label = label_item.text()
        detail = detail_item.text() if detail_item is not None else ""
        return "{} - {}".format(label, detail).rstrip(" -")

    def _set_clipboard(self, text: str) -> None:
        QtWidgets.QApplication.clipboard().setText(text)

    def _update_items_view_height(self) -> None:
        """Keep the preview at least as tall as the entries it shows."""
        rows = self._items_model.rowCount()
        if not rows:
            self._items_view.setMinimumHeight(0)
            return

        row_height = self._items_view.sizeHintForRow(0)
        if row_height <= 0:
            row_height = 24
        frame = 2 * self._items_view.frameWidth()
        self._items_view.setMinimumHeight(
            min(rows * row_height + frame + 4, MAX_PREVIEW_HEIGHT)
        )

    def _set_hint(self, hint: Optional[str], is_error: bool) -> None:
        self._hint_label.setText(hint or "")
        self._warning_label.setVisible(bool(hint) and is_error)
        self._hint_widget.setVisible(bool(hint))
