from __future__ import annotations

from enum import Enum
import json
from pathlib import Path
import sys
from typing import Any

from qtpy import QtWidgets

import ui_preview_setup  # noqa: F401

from ayon_core.ui.style_types import get_ayon_style

from ayon_core.ui.data_models import (
    CommentModel,
    VersionPublishModel,
    StatusChangeModel,
    ProjectData,
    User,
    Team,
    CommentCategory,
    VersionData,
    ActivityData,
)


class Style(Enum):
    Base = 0
    CSS = 1
    AYONStyle = 2
    AYONStyleOverCSS = 3


CURRENT_DIR = Path(__file__).parent
REPO_ROOT = Path(CURRENT_DIR).parent
RESOURCES_DIR = CURRENT_DIR / "resources"

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


def get_test_data_dir() -> Path:
    """
    As we moved all resources
    from `tests/client/ayon_core/ui` to `tests/client/ayon_core/ui/test_data`
    we need to be able to find the test data directory.
    """

    # Relative to repo root path tests/client/ayon_core/ui/test_data
    return (
        REPO_ROOT / "tests" / "client" / "ayon_core" / "ui" / "test_data"
    )


def get_resources_dir() -> Path:
    return CURRENT_DIR / "resources"


def load_rv_stylesheet(old: bool = True) -> str:
    filename = "rv_mac_dark_legacy.qss" if old else "rv_dark.qss"
    fpath = RESOURCES_DIR / filename
    print(f"Loading stylesheet from {fpath}")
    return fpath.read_text(encoding="utf-8")


def preview_widget(
    create_widget_func, style: Style = Style.AYONStyleOverCSS
) -> None:
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
    widget = create_widget_func()

    if style == Style.AYONStyleOverCSS:
        widget.setStyle(get_ayon_style())

    widget.show()

    print("Qt widget preview started. Close the window to exit.")
    return app.exec()


def read_json_file(fpath: Path):
    return json.loads(fpath.read_text(encoding="utf-8"))


def process_test_project_data(project_data: dict) -> ProjectData:
    # convert users
    for user in list(project_data["users"]):
        um = User(**user)
        project_data["users"].remove(user)
        project_data["users"].append(um)
    # convert teams
    for team in list(project_data["teams"]):
        tm = Team(**team)
        project_data["teams"].remove(team)
        project_data["teams"].append(tm)
    # convert comment categories
    for comcat in list(project_data["comment_category"]):
        cc = CommentCategory(**comcat)
        project_data["comment_category"].remove(comcat)
        project_data["comment_category"].append(cc)
    # convert current_user
    project_data["current_user"] = User(**project_data["current_user"])
    data_model = ProjectData(**project_data)
    return data_model


def process_test_version_data(version_data: dict) -> VersionData:
    vd = VersionData(**version_data)
    return vd


def process_test_activity_data(activity_data) -> ActivityData:
    # convert activities
    for act in list(activity_data["activity_list"]):
        act.pop("short_date")
        atype = act.pop("type")
        # print(f">> {atype}:  {act}")
        am = None
        if atype == "comment":
            am = CommentModel(**act)
        elif atype == "version.publish":
            am = VersionPublishModel(**act)
        elif atype == "status.change":
            am = StatusChangeModel(**act)
        else:
            err = f"Unknown type: {atype!r}"
            raise ValueError(err)
        activity_data["activity_list"].remove(act)
        activity_data["activity_list"].append(am)
    # print(json.dumps(activity_data, indent=4, default=str))
    activity_data.pop("hash")
    ad = ActivityData(**activity_data)
    return ad


def get_test_project_data() -> ProjectData:
    # read project data
    project_file = RESOURCES_DIR / "sample_project_data.json"
    project_data = read_json_file(project_file)
    print(f"[test]  read: {project_file}")  # noqa: T201
    return process_test_project_data(project_data)


def get_test_version_data() -> VersionData:
    version_data_file = RESOURCES_DIR / "sample_version_data.json"
    version_data = read_json_file(version_data_file)
    print(f"[test]  read: {version_data_file}")  # noqa: T201
    return process_test_version_data(version_data)


def get_test_activity_data() -> ActivityData:
    activity_file = RESOURCES_DIR / "sample_activities.json"
    activity_data = read_json_file(activity_file)
    print(f"[test]  read: {activity_file}")  # noqa: T201
    return process_test_activity_data(activity_data)


def _load_statuses() -> list[dict[str, Any]]:
    statuses_file = get_test_data_dir() / "sample_statuses.json"
    statuses_data = read_json_file(statuses_file)
    print(f"[test]  read: {statuses_file}")  # noqa: T201
    return statuses_data


EXAMPLE_STATUSES = _load_statuses()
