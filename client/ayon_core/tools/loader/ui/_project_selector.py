"""Project model and selector combo-box for the reviews panel."""

from __future__ import annotations

import json
from typing import Any

from ayon_ui_qt.components.combo_box import AYComboBox
from ayon_ui_qt.style import get_ayon_style_data
from qtpy import QtCore, QtGui

from ayon_core.lib import Logger
from ayon_core.tools.loader.ui.review_controller import ReviewController
from ayon_core.tools.utils import get_qt_icon

log = Logger.get_logger(__name__)


class ProjectModel(QtGui.QStandardItemModel):
    """Model that lists all active AYON projects."""

    ShortTextRole = QtCore.Qt.ItemDataRole.UserRole + 1
    IconNameRole = QtCore.Qt.ItemDataRole.UserRole + 2

    def __init__(
        self, controller: ReviewController, *args: Any, **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self._style_data = get_ayon_style_data("QComboBox", "low")
        log.debug("Style data: %s", json.dumps(self._style_data))

        projects = controller.fetch_projects()
        fg_color = self._style_data.get("color", "#ee5555")
        bg_color = self._style_data.get("background-color", "#550000")
        log.debug("FG: %s, BG: %s", fg_color, bg_color)

        fgc = QtGui.QColor(fg_color)
        bgc = QtGui.QColor(bg_color)
        project_icon = {
            "type": "material-symbols",
            "name": "map",
            "color": fg_color,
        }

        for project in projects:
            if not project.get("active", True):
                continue
            item = QtGui.QStandardItem(project["name"])
            icon = get_qt_icon(project_icon)
            if icon:
                item.setIcon(icon)
            item.setData(
                QtGui.QBrush(fgc),
                QtCore.Qt.ItemDataRole.ForegroundRole,
            )
            item.setData(
                QtGui.QBrush(bgc),
                QtCore.Qt.ItemDataRole.BackgroundRole,
            )
            item.setData("map", self.IconNameRole)
            item.setData(project["name"], self.ShortTextRole)
            self.appendRow(item)


class ProjectSelector(AYComboBox):
    """Combo box that lets the user select an AYON project."""

    def __init__(
        self,
        controller: ReviewController,
        *args: Any,
        initial_project: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            *args,
            inverted=False,
            variant=AYComboBox.Variants.Low,
            **kwargs,
        )
        self.setModel(ProjectModel(controller, self))
        if initial_project:
            self.setCurrentText(initial_project)

    def current_project(self) -> str:
        """Return the currently selected project name."""
        return self.currentText()
