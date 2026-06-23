from __future__ import annotations

import logging
import json
from pathlib import Path
from .data_models import (
    CommentModel,
    VersionPublishModel,
    StatusChangeModel,
    ProjectData,
    User,
    Team,
    CommentCategory,
    VersionData,
    ActivityData,
    AnnotationModel,
    FileModel,
)
from qtpy.QtGui import QColor

logger = logging.getLogger(__name__)


def color_blend(bg: str, fg: str, mix: float):
    b = QColor(bg)
    t = QColor(fg)
    o = mix
    io = 1.0 - o
    return QColor(
        int(b.red() * io + t.red() * o),
        int(b.green() * io + t.green() * o),
        int(b.blue() * io + t.blue() * o),
    )


def process_activity_data(
    activity_data: dict, project_data: ProjectData
) -> list[CommentModel | VersionPublishModel | StatusChangeModel]:
    """Preprocesses payload data to extract and parse comment activities.

    This function processes the input data to extract activities, specifically
    focusing on comment activities. It parses these activities using the
    AYComment class and returns a list of parsed comment objects.

    Args:
        activity_data (dict): The input data containing project activities in
            a specific structure. Expected to have a nested structure with
            'project' -> 'activities'.
        project_data (ProjectData)

    Returns:
        list: A list of parsed comment objects. Returns an empty list if
            no activities are found or if there's an error during processing.
    """
    try:
        activities: list[dict] = activity_data["project"]["activities"]
    except KeyError as err:
        logger.error(f"Could not extract activities: {err}")
        return []

    users = {d.short_name: d for d in project_data.users}
    category_colors = {c.name: c.color for c in project_data.comment_category}

    ui_data = []
    nothing = "n/a"
    for act in activities:
        act_data = act.get("activityData", {})
        if isinstance(act_data, str):
            act_data = json.loads(act_data)
            act["activityData"] = act_data

        activity_type = act.get("activityType", "")
        activity_id = act["activityId"]

        user_name = act.get("author", {}).get("name", nothing)
        user_full_name = user_name
        user = users.get(user_name)
        if user:
            user_full_name = user.full_name

        date = act.get("updatedAt", nothing)

        if activity_type == "comment":
            annotation_models, ranges = _parse_annotations(act_data, nothing)
            file_models = _parse_files(act, ranges, nothing)
            category = act_data.get("category", "")
            ui_data.append(
                CommentModel(
                    activity_id=activity_id,
                    user_full_name=user_full_name,
                    user_name=user_name,
                    comment=act.get("body", nothing),
                    comment_date=date,
                    category=category,
                    category_color=category_colors.get(category, ""),
                    files=file_models,
                    annotations=annotation_models,
                )
            )
        elif activity_type == "version.publish":
            ui_data.append(
                VersionPublishModel(
                    activity_id=activity_id,
                    user_full_name=user_full_name,
                    user_name=user_name,
                    version=str(
                        act_data.get("origin", {}).get("name", nothing)
                    ),
                    product=str(
                        act_data.get("context", {}).get("productName", nothing)
                    ),
                    date=date,
                )
            )
        elif activity_type == "status.change":
            version = act_data.get("origin", {}).get("name", nothing)
            parents: list[dict] = act_data.get("parents", {})
            product = next(
                (p["name"] for p in parents if p["type"] == "product"),
                nothing,
            )
            ui_data.append(
                StatusChangeModel(
                    activity_id=activity_id,
                    user_full_name=user_full_name,
                    user_name=user_name,
                    product=product,
                    version=version,
                    old_status=str(act_data.get("oldValue", nothing)),
                    new_status=str(act_data.get("newValue", nothing)),
                    date=date,
                )
            )

    return ui_data


def _parse_files(act, ranges, nothing):
    """Attached files to comment activities."""
    files = act.get("files", [])
    file_models = []
    for file_info in files:
        fid = file_info.get("id", nothing)
        file_models.append(
            FileModel(
                id=fid,
                mime=file_info.get("mime", nothing),
                frame=ranges.get(fid, (-1, -1))[0],
            )
        )
    return file_models


def _parse_annotations(act_data, nothing):
    """Attached annotations to comment activities."""
    ranges = {}
    annotation_models = []
    annotations = act_data.get("annotations", [])
    for annotation in annotations:
        annotation_models.append(
            AnnotationModel(
                id=annotation.get("id", nothing),
                range=annotation.get("range", nothing),
                composite=annotation.get("composite", nothing),
                transparent=annotation.get("transparent", nothing),
            )
        )
        ranges[annotation.get("composite")] = annotation.get("range")
        ranges[annotation.get("transparent")] = annotation.get("range")
    return annotation_models, ranges


def clear_layout(layout):
    """Recursively deletes child QWidgets in the initial QLayout and in
    sub-layouts.

    This function handles all types of QLayout subclasses (QVBoxLayout,
    QHBoxLayout, QGridLayout, etc.) and safely deletes all child widgets
    while maintaining the integrity of the parent layout structure.

    Args:
        layout: QLayout instance to clear
    """
    if layout is None:
        return

    # print(f"layout = {layout}")

    # Work backwards through the layout to avoid index issues when removing
    # items
    for i in reversed(range(layout.count())):
        item = layout.takeAt(i)
        if item is None:
            continue

        widget = item.widget()
        sub_layout = item.layout()

        if widget:
            # Recursively clear any layouts this widget might have
            # (in case it's a container widget with its own layouts)
            if hasattr(widget, "layout") and widget.layout():
                clear_layout(widget.layout())
            # Delete the widget
            widget.setParent(None)
            widget.deleteLater()
        elif sub_layout:
            # Recursively clear the sub-layout
            clear_layout(sub_layout)
            # Delete the layout
            sub_layout.deleteLater()


def read_json_file(fpath):
    import json

    with open(fpath, "r") as fr:  # noqa: PLW1514, UP015
        data = json.load(fr)
    return data


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


def get_test_project_data() -> ProjectData:
    # read project data
    from . import _get_test_data_dir

    file_dir = _get_test_data_dir() or Path(__file__).parent
    project_file = file_dir / "sample_project_data.json"
    project_data = read_json_file(project_file)
    print(f"[test]  read: {project_file}")  # noqa: T201
    return process_test_project_data(project_data)


def process_test_version_data(version_data: dict) -> VersionData:
    vd = VersionData(**version_data)
    return vd


def get_test_version_data() -> VersionData:
    from . import _get_test_data_dir

    file_dir = _get_test_data_dir() or Path(__file__).parent
    version_data_file = file_dir / "sample_version_data.json"
    version_data = read_json_file(version_data_file)
    print(f"[test]  read: {version_data_file}")  # noqa: T201
    return process_test_version_data(version_data)


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


def get_test_activity_data() -> ActivityData:
    from . import _get_test_data_dir

    file_dir = _get_test_data_dir() or Path(__file__).parent
    activity_file = file_dir / "sample_activities.json"
    activity_data = read_json_file(activity_file)
    print(f"[test]  read: {activity_file}")  # noqa: T201
    return process_test_activity_data(activity_data)


if __name__ == "__main__":
    pd = get_test_project_data()
    print(f"pd.project_name = {pd.project_name}")
    print(f"pd.users = {pd.users}")
    print(f"pd.teams = {pd.teams}")
    # print(f"pd.anatomy = {pd.anatomy}")
    print()
    vd = get_test_version_data()
    print(f"{vd}")
    print()
    ad = get_test_activity_data()
    print(f"{ad}")
