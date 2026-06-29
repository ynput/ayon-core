from qtpy import QtWidgets, QtCore, QtGui

from ayon_core.ui.components import (
    AYButton,
    AYLabel,
    AYHBoxLayout,
    AYVBoxLayout
)

from ayon_core.style import load_stylesheet, get_app_icon_path
from ayon_core.pipeline.workfile.lock_workfile import get_workfile_lock_data


class WorkfileLockDialog(QtWidgets.QDialog):
    def __init__(self, workfile_path, parent=None):
        super(WorkfileLockDialog, self).__init__(parent)
        self.setWindowTitle("Warning")
        icon = QtGui.QIcon(get_app_icon_path())
        self.setWindowIcon(icon)

        data = get_workfile_lock_data(workfile_path)

        message = "{} on {} machine is working on the same workfile.".format(
            data["username"],
            data["hostname"]
        )

        msg_label = AYLabel(message, parent=self)

        btns_widget = QtWidgets.QWidget(self)

        cancel_btn = AYButton(
            "Cancel", variant=AYButton.Variants.Tertiary,
            parent=btns_widget,
        )
        ignore_btn = AYButton(
            "Ignore lock", variant=AYButton.Variants.Danger,
            parent=btns_widget,
        )

        btns_layout = AYHBoxLayout(btns_widget, margin=0, spacing=10)
        btns_layout.addStretch(1)
        btns_layout.addWidget(cancel_btn, 0)
        btns_layout.addWidget(ignore_btn, 0)

        main_layout = AYVBoxLayout(self, margin=15, spacing=4)
        main_layout.addWidget(msg_label, 1, QtCore.Qt.AlignCenter),
        main_layout.addSpacing(10)
        main_layout.addWidget(btns_widget, 0)

        cancel_btn.clicked.connect(self.reject)
        ignore_btn.clicked.connect(self.accept)

    def showEvent(self, event):
        super(WorkfileLockDialog, self).showEvent(event)

        self.setStyleSheet(load_stylesheet())
