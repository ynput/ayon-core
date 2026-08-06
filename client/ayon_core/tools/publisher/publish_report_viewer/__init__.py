from qtpy import QtWidgets

from .widgets import PublishReportViewerWidget
from .window import PublishReportViewerWindow


__all__ = (
    "PublishReportViewerWidget",
    "PublishReportViewerWindow",
    "main",
)


def main():
    app = QtWidgets.QApplication([])
    window = PublishReportViewerWindow()
    window.show()
    return app.exec_()
