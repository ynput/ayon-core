"""Minimal QColorDialog-based picker with default and user swatches."""

import json
from qtpy import QtWidgets, QtCore, QtGui

_USER_SWATCHES_KEY = "swatches"
_USER_SWATCHES_CAP = 24
_SETTINGS_ORG = "ayon-core"
_SETTINGS_APP = "color_picker"

# Default swatches shown for all users (hex, optional name).
DEFAULT_SWATCHES = [
    {"hex": "#000000", "name": "Black"},
    {"hex": "#ffffff", "name": "White"},
    {"hex": "#808080", "name": "Gray"},
    {"hex": "#ff0000", "name": "Red"},
    {"hex": "#00ff00", "name": "Green"},
    {"hex": "#0000ff", "name": "Blue"},
    {"hex": "#ffff00", "name": "Yellow"},
    {"hex": "#ff00ff", "name": "Magenta"},
    {"hex": "#00ffff", "name": "Cyan"},
]


def _hex_from_value(value):
    """Normalize input to #rrggbb hex string. Returns None if invalid."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        c = QtGui.QColor(int(value[0]), int(value[1]), int(value[2]))
        return c.name() if c.isValid() else None
    if isinstance(value, QtGui.QColor):
        return value.name() if value.isValid() else None
    if isinstance(value, str):
        c = QtGui.QColor(value)
        return c.name() if c.isValid() else None
    return None


def _load_user_swatches():
    settings = QtCore.QSettings(
        QtCore.QSettings.IniFormat,
        QtCore.QSettings.UserScope,
        _SETTINGS_ORG,
        _SETTINGS_APP,
    )
    raw = settings.value(_USER_SWATCHES_KEY)
    if not raw:
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return data if isinstance(data, list) else []
    except (TypeError, ValueError):
        return []


def _save_user_swatches(swatches):
    settings = QtCore.QSettings(
        QtCore.QSettings.IniFormat,
        QtCore.QSettings.UserScope,
        _SETTINGS_ORG,
        _SETTINGS_APP,
    )
    settings.setValue(_USER_SWATCHES_KEY, json.dumps(swatches))
    settings.sync()


class _SwatchButton(QtWidgets.QPushButton):
    """Single swatch: color background, tooltip from name or hex."""

    def __init__(self, hex_str, name=None, is_user_swatch=False, parent=None):
        super().__init__(parent)
        self._hex = hex_str
        self._name = (name or "").strip()
        self._is_user_swatch = is_user_swatch
        self.setFixedSize(22, 22)
        self.setToolTip(self._name if self._name else hex_str)
        self._update_style()

    def _update_style(self):
        self.setStyleSheet(
            "QPushButton { background-color: %s; border: 1px solid #555; } "
            "QPushButton:hover { border: 1px solid #888; }" % self._hex
        )

    def hex_value(self):
        return self._hex

    def is_user_swatch(self):
        return self._is_user_swatch


class SimpleColorPicker(QtWidgets.QWidget):
    """Dialog button plus default and user swatch rows."""

    value_changed = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_hex = "#000000"
        self._user_swatches = []  # list of {"hex", "name"}
        self._swatch_buttons = []  # _SwatchButton instances
        self._block_signals = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._color_btn = QtWidgets.QPushButton(self)
        self._color_btn.setFixedHeight(24)
        self._color_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self._color_btn.clicked.connect(self._on_color_button_clicked)
        self._update_color_button_style()
        layout.addWidget(self._color_btn)

        swatch_layout = QtWidgets.QHBoxLayout()
        swatch_layout.setSpacing(4)
        swatch_widget = QtWidgets.QWidget(self)
        swatch_widget.setLayout(swatch_layout)

        self._default_swatch_container = QtWidgets.QWidget(self)
        self._default_swatch_layout = QtWidgets.QHBoxLayout(
            self._default_swatch_container
        )
        self._default_swatch_layout.setContentsMargins(0, 0, 0, 0)
        self._default_swatch_layout.setSpacing(4)
        swatch_layout.addWidget(self._default_swatch_container)

        self._user_swatch_container = QtWidgets.QWidget(self)
        self._user_swatch_layout = QtWidgets.QHBoxLayout(
            self._user_swatch_container
        )
        self._user_swatch_layout.setContentsMargins(0, 0, 0, 0)
        self._user_swatch_layout.setSpacing(4)
        swatch_layout.addWidget(self._user_swatch_container)

        add_btn = QtWidgets.QPushButton("+", self)
        add_btn.setFixedSize(22, 22)
        add_btn.setToolTip("Add current color to swatches")
        add_btn.clicked.connect(self._on_add_swatch)
        swatch_layout.addWidget(add_btn)

        layout.addWidget(swatch_widget)

        self._user_swatches = _load_user_swatches()
        self._rebuild_swatches()

    def _update_color_button_style(self):
        self._color_btn.setStyleSheet(
            "QPushButton { background-color: %s; border: 1px solid #555; } "
            "QPushButton:hover { border: 1px solid #888; }" % self._current_hex
        )

    def _on_color_button_clicked(self):
        initial = QtGui.QColor(self._current_hex)
        color = QtWidgets.QColorDialog.getColor(initial, self, "Choose color")
        if color.isValid():
            self._set_hex(color.name())

    def _set_hex(self, hex_str):
        if hex_str == self._current_hex:
            return
        self._current_hex = hex_str
        self._update_color_button_style()
        if not self._block_signals:
            self.value_changed.emit(self._current_hex)

    def _rebuild_swatches(self):
        for btn in self._swatch_buttons:
            btn.deleteLater()
        self._swatch_buttons.clear()

        while self._default_swatch_layout.count():
            item = self._default_swatch_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        while self._user_swatch_layout.count():
            item = self._user_swatch_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for item in DEFAULT_SWATCHES:
            hex_val = item.get("hex", "#000000")
            name = item.get("name")
            btn = _SwatchButton(
                hex_val, name, is_user_swatch=False, parent=self
            )
            btn.clicked.connect(
                lambda checked=False, h=hex_val: self._set_hex(h)
            )
            self._default_swatch_layout.addWidget(btn)
            self._swatch_buttons.append(btn)

        for item in self._user_swatches:
            hex_val = item.get("hex", "#000000")
            name = item.get("name", "")
            btn = _SwatchButton(
                hex_val, name, is_user_swatch=True, parent=self
            )
            btn.clicked.connect(
                lambda checked=False, h=hex_val: self._set_hex(h)
            )
            btn.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, b=btn: self._on_user_swatch_context(pos, b)
            )
            self._user_swatch_layout.addWidget(btn)
            self._swatch_buttons.append(btn)

    def _on_user_swatch_context(self, pos, swatch_btn):
        if not swatch_btn.is_user_swatch():
            return
        menu = QtWidgets.QMenu(self)
        action = QtWidgets.QAction("Remove swatch", self)
        action.triggered.connect(
            lambda: self._remove_user_swatch(swatch_btn.hex_value())
        )
        menu.addAction(action)
        menu.exec_(swatch_btn.mapToGlobal(pos))

    def _remove_user_swatch(self, hex_str):
        self._user_swatches = [
            s for s in self._user_swatches if s.get("hex") != hex_str
        ]
        _save_user_swatches(self._user_swatches)
        self._rebuild_swatches()

    def _on_add_swatch(self):
        if len(self._user_swatches) >= _USER_SWATCHES_CAP:
            return
        name, ok = QtWidgets.QInputDialog.getText(
            self,
            "Add swatch",
            "Name (optional):",
            QtWidgets.QLineEdit.Normal,
            "",
        )
        if not ok:
            return
        name = (name or "").strip()
        entry = {"hex": self._current_hex, "name": name}
        if entry in self._user_swatches:
            return
        self._user_swatches.append(entry)
        _save_user_swatches(self._user_swatches)
        self._rebuild_swatches()

    def set_value(self, value):
        hex_str = _hex_from_value(value)
        if hex_str:
            self._current_hex = hex_str
            self._update_color_button_style()

    def current_value(self):
        return self._current_hex
