"""Report of the last workfile template build."""

from __future__ import annotations

from typing import Optional

from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.ui.components import (
    AYButton,
    AYContainer,
    AYLabel,
    AYTreeView,
)

ERROR_COLOR = "#e55353"

STATUS_LABELS = {
    "pending": "PENDING",
    "running": "RUNNING",
    "succeeded": "OK",
    "failed": "FAILED",
}


class BuildReportDialog(QtWidgets.QDialog):
    """Report of the last template build.

    Shows the placeholders that were processed in the order they were
    processed, their status, duration and error. The captured build log
    is available in a separate tab.

    Args:
        controller (WorkfileTemplateBuilderController): Tool controller.
        parent (Optional[QtWidgets.QWidget]): Parent widget.

    """

    def __init__(
        self,
        controller,
        parent: Optional[QtWidgets.QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Workfile Template Build Report")
        self.resize(780, 540)

        self._controller = controller

        title_label = AYLabel(
            "Build report",
            parent=self,
            bold=True,
            rel_text_size=2,
        )
        summary_label = AYLabel(parent=self, dim=True)

        model = QtGui.QStandardItemModel()
        model.setHorizontalHeaderLabels(
            ["Order", "Placeholder", "Status", "Duration"]
        )

        view = AYTreeView(self, variant=AYTreeView.Variants.Low)
        view.setModel(model)
        view.setRootIsDecorated(False)
        view.setIndentation(0)
        view.setAllColumnsShowFocus(True)
        view.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        header = view.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)

        details_label = AYLabel("Details", parent=self, dim=True)
        details_view = QtWidgets.QPlainTextEdit(self)
        details_view.setReadOnly(True)
        details_view.setMinimumHeight(90)

        steps_widget = QtWidgets.QWidget(self)
        steps_layout = QtWidgets.QVBoxLayout(steps_widget)
        steps_layout.setContentsMargins(0, 0, 0, 0)
        steps_layout.addWidget(view, 1)
        steps_layout.addWidget(details_label)
        steps_layout.addWidget(details_view)

        log_view = QtWidgets.QPlainTextEdit(self)
        log_view.setReadOnly(True)
        log_view.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)

        tabs = QtWidgets.QTabWidget(self)
        tabs.addTab(steps_widget, "Steps")
        tabs.addTab(log_view, "Log")

        copy_report_btn = AYButton(
            "Copy report",
            parent=self,
            variant=AYButton.Variants.Surface,
            icon="content_copy",
        )
        copy_log_btn = AYButton(
            "Copy log",
            parent=self,
            variant=AYButton.Variants.Surface,
            icon="content_copy",
        )
        close_btn = AYButton(
            "Close",
            parent=self,
            variant=AYButton.Variants.Filled,
            icon="close",
        )
        btns_widget = AYContainer(
            self,
            layout=AYContainer.Layout.HBox,
            layout_spacing=6,
        )
        btns_widget.addStretch(1)
        btns_widget.add_widget(copy_report_btn)
        btns_widget.add_widget(copy_log_btn)
        btns_widget.add_widget(close_btn)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(title_label)
        layout.addWidget(summary_label)
        layout.addWidget(tabs, 1)
        layout.addWidget(btns_widget)

        view.selectionModel().selectionChanged.connect(
            self._on_selection_change
        )
        copy_report_btn.clicked.connect(self._on_copy_report)
        copy_log_btn.clicked.connect(self._on_copy_log)
        close_btn.clicked.connect(self.accept)

        self._model = model
        self._view = view
        self._tabs = tabs
        self._summary_label = summary_label
        self._details_view = details_view
        self._log_view = log_view

        self.refresh()

    def refresh(self) -> None:
        """Reload steps and log of the last build from the controller."""
        steps = self._controller.get_build_steps()
        self._model.removeRows(0, self._model.rowCount())

        total_duration = 0.0
        failed = 0
        for step in steps:
            total_duration += step.duration
            if step.error:
                failed += 1

            order_item = QtGui.QStandardItem(str(step.order))
            label_item = QtGui.QStandardItem(step.label)
            status_item = QtGui.QStandardItem(
                STATUS_LABELS.get(step.status, step.status)
            )
            duration_item = QtGui.QStandardItem(
                "{:.2f}s".format(step.duration)
            )
            for item in (order_item, label_item, status_item, duration_item):
                item.setEditable(False)
                item.setData(step.error, QtCore.Qt.UserRole)

            if step.error:
                color = QtGui.QColor(ERROR_COLOR)
                status_item.setForeground(QtGui.QBrush(color))
                label_item.setForeground(QtGui.QBrush(color))

            self._model.appendRow([
                order_item, label_item, status_item, duration_item
            ])

        if steps:
            self._summary_label.setText(
                "{} placeholder(s) processed, {} failed, {:.2f}s total".format(
                    len(steps), failed, total_duration
                )
            )
        else:
            self._summary_label.setText("No build was run yet.")

        log_lines = self._controller.get_build_log()
        self._log_view.setPlainText("\n".join(log_lines))

        self._details_view.setPlainText("")
        if steps:
            index = self._model.index(0, 0)
            self._view.setCurrentIndex(index)
            self._view.selectionModel().select(
                index,
                QtCore.QItemSelectionModel.ClearAndSelect
                | QtCore.QItemSelectionModel.Rows,
            )

    def get_report_text(self) -> str:
        """Plain text report of the last build."""
        lines = [self._summary_label.text()]
        for step in self._controller.get_build_steps():
            lines.append(
                "[{}] order={} {} ({}) {:.2f}s".format(
                    STATUS_LABELS.get(step.status, step.status),
                    step.order,
                    step.label,
                    step.scene_identifier,
                    step.duration,
                )
            )
            if step.error:
                lines.append(step.error)
        return "\n".join(lines)

    def _on_selection_change(self) -> None:
        indexes = self._view.selectionModel().selectedRows()
        if not indexes:
            self._details_view.setPlainText("")
            return
        error = indexes[0].data(QtCore.Qt.UserRole) or ""
        self._details_view.setPlainText(error if error else "No errors.")

    def _on_copy_report(self) -> None:
        QtWidgets.QApplication.clipboard().setText(self.get_report_text())

    def _on_copy_log(self) -> None:
        QtWidgets.QApplication.clipboard().setText(
            "\n".join(self._controller.get_build_log())
        )


__all__ = (
    "BuildReportDialog",
)
