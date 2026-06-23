import sys
from enum import Enum
from pathlib import Path

from qtpy import QtWidgets

# from .style import AYONStyle
from .style_types import get_ayon_style


class Style(Enum):
    Base = 0
    CSS = 1
    AYONStyle = 2
    AYONStyleOverCSS = 3


AWFUL_CSS = """
QWidget {
    background-color: #441e1e;
    color: #F4F5F5;
    margin: 0px;
    padding: 0px;
    border: 0px;
}
QLabel {
    color: #F4F5F5;
}
QPushButton {
    border-color: #acf;
    border-width: 2px;
    border-style: solid;
}
"""


def load_rv_stylesheet(old=True):
    fpath = Path(__file__).parent.joinpath(
        "resources", "rv_mac_dark_legacy.qss" if old else "rv_dark.qss"
    )
    print(f"Loading stylesheet from {fpath}")
    with open(fpath, "r") as fr:
        return fr.read()


def test(test_widget, style: Style = Style.AYONStyleOverCSS):
    """Main function to run the Qt test."""
    app = QtWidgets.QApplication(sys.argv)

    if style == Style.CSS:
        # Set old RV dark theme for the application
        app.setStyleSheet(load_rv_stylesheet())
    elif style == Style.AYONStyle:
        app.setStyle(get_ayon_style())
    elif style == Style.AYONStyleOverCSS:
        app.setStyleSheet(load_rv_stylesheet())

    # Create and show the test widget
    widget = test_widget()

    if style == Style.AYONStyleOverCSS:
        widget.setStyle(get_ayon_style())

    widget.show()

    print("Qt widget test started. Close the window to exit.")
    return app.exec()
