from typing import Any
import json

from qtpy import QtCore, QtGui, QtWidgets

from ayon_ui_qt import get_ayon_style, get_ayon_style_data
from ayon_ui_qt.components.container import AYContainer
from ayon_ui_qt.components.label import AYLabel
from ayon_ui_qt.components.buttons import AYButton
from ayon_ui_qt.components.combo_box import AYComboBox
from ayon_ui_qt.components.tree_model import LazyTreeModel, TreeNode
from ayon_ui_qt.components.tree_view import AYTreeView
from ayon_ui_qt.components.slicer import AYSlicer

import ayon_api
from ayon_api.graphql_queries import projects_graphql_query
from ayon_core.tools.utils import get_qt_icon


class ProjectModel(QtGui.QStandardItemModel):
    ShortTextRole = QtCore.Qt.ItemDataRole.UserRole + 1
    IconNameRole = QtCore.Qt.ItemDataRole.UserRole + 2

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # print(f"PID: {QtCore.QCoreApplication.instance().applicationPid()}")
        self._style_data = get_ayon_style_data("QComboBox", "low")
        print(f"STYLE DATA: {json.dumps(self._style_data)}")
        projects = self._fetch_graphql_projects()
        # print(f"PROJECT: {json.dumps(projects, indent=4)}")

        fg_color = self._style_data.get("color", "#ee5555")
        bg_color = self._style_data.get("background-colore", "#550000")
        print(f"FG: {fg_color}, BG: {bg_color}")
        fgc = QtGui.QColor(fg_color)
        bgc = QtGui.QColor(bg_color)

        PROJECT_ICON = {
            "type": "material-symbols",
            "name": "map",
            "color": fg_color,
        }

        for project in projects:
            if not project.get("active", True):
                continue
            item = QtGui.QStandardItem(project["name"])
            icon = get_qt_icon(PROJECT_ICON)
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

    def _fetch_graphql_projects(self) -> list[dict[str, Any]]:
        """Fetch projects using GraphQl.

        This method was added because ayon_api had a bug in 'get_projects'.

        Returns:
            list[dict[str, Any]]: List of projects.

        """
        api = ayon_api.get_server_api_connection()
        query = projects_graphql_query({"name", "active", "library", "data"})

        projects = []
        for parsed_data in query.continuous_query(api):  # type: ignore
            for project in parsed_data["projects"]:
                project_data = project["data"]
                if project_data is None:
                    project["data"] = {}
                elif isinstance(project_data, str):
                    project["data"] = json.loads(project_data)
                projects.append(project)
        return projects


class ProjectSelector(AYComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            inverted=False,
            variant=AYComboBox.Variants.Low,
            **kwargs,
        )
        # self.setAutoFillBackground(False)

        self.setModel(ProjectModel(self))

    def current_project(self):
        return self.currentText()


class ReviewTreeModel(LazyTreeModel):
    def __init__(self, parent) -> None:
        super().__init__(parent)


class ReviewTreeView(AYTreeView):
    def __init__(self, parent) -> None:
        super().__init__(parent, variant=AYTreeView.Variants.Low)


class ReviewSlicer(AYContainer):
    CATEGORIES = [
        {
            "text": "Products",
            "short_text": "PRD",
            "icon": "photo_library",
            "color": "#f4f5f5",
        },
        {
            "text": "Reviews",
            "short_text": "REV",
            "icon": "subscriptions",
            "color": "#f4f5f5",
        },
    ]
    category_changed = QtCore.Signal(str)

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.Low,
            layout_margin=8,
            layout_spacing=8,
            **kwargs,
        )
        self._selector = ProjectSelector()
        self.add_widget(self._selector, stretch=0)

        self._slicer = AYSlicer(item_list=self.CATEGORIES)
        self.add_widget(self._slicer, stretch=0)

        self._tree_view = ReviewTreeView(self)
        self.add_widget(self._tree_view, stretch=0)

        self._slicer.category_changed.connect(self._on_category_changed)

    def set_model(self, model: LazyTreeModel):
        self._tree_view.setModel(model)
        self._slicer.set_model(self._tree_view.model(), view=self._tree_view)

    def _on_category_changed(self, category: str):
        self.category_changed.emit(category)

    def current_category(self):
        return self._slicer.current_category()

    def current_project(self):
        return self._selector.current_project()


class ReviewTable(AYContainer):
    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.Low,
            **kwargs,
        )
        self.add_widget(AYLabel("nothing yet"))


class ReviewsWidget(AYContainer):
    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.High,
            **kwargs,
        )
        self._folder_type_icons = {}
        self._slicer = ReviewSlicer(self)
        self._current_category = self._slicer.current_category()
        self._review_data = []
        self._model = LazyTreeModel(fetch_children=self._fetch_children)
        self._slicer.set_model(self._model)

        self._table = ReviewTable(self)
        self._build()


        #  connect signals
        self._slicer._selector.currentTextChanged.connect(
            self.on_project_changed
        )
        self._slicer.category_changed.connect(self._on_category_changed)

    def _build(self):
        main_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        main_splitter.addWidget(self._slicer)
        main_splitter.addWidget(self._table)
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 8)
        self.add_widget(main_splitter)

    def _fetch_children(self, parent_id):
        if not self._folder_type_icons:
            self._folder_type_icons = self._build_folder_type_icons(
                self._current_project()
            )
        if self._current_category == "Products":
            return self._fetch_products(parent_id)
        return self._fetch_reviews(parent_id)

    def _fetch_reviews(self, parent_id):
        print(f"Fetching children for {parent_id}")
        if not self._review_data:
            self._get_reviews()
        if parent_id is None:
            nodes = []
            for r in self._review_data:
                if not r.get("entityListType", None) == "review-session":
                    continue
                nodes.append(
                    TreeNode(
                        id=r.get("id", "no id"),
                        label=r.get("label", "no label"),
                        has_children=False,
                        icon="subscriptions",
                        data=r,
                    )
                )
            return nodes
        return []

    def _fetch_products(self, parent_id):
        """Fetch folder hierarchy level by parent folder id."""
        print(f"Fetching children for {parent_id}")
        project = self._current_project()
        if not project:
            return []

        # parent_id=None → root-level folders (parent_ids=[None]
        # means "direct children of project")
        folders = ayon_api.get_folders(
            project,
            parent_ids=[parent_id],
            fields={
                "id",
                "name",
                "label",
                "folderType",
                "hasChildren",
                "hasTasks",
            },
        )

        # Fall back to generic "folder" if type not in anatomy
        type_icons = getattr(self, "_folder_type_icons", {})
        # print(f"  --  {type_icons}")

        return [
            TreeNode(
                id=f["id"],
                label=f.get("label") or f["name"],
                has_children=f.get("hasChildren", False),
                icon=type_icons.get(f.get("folderType", ""), "folder"),
                data=f,
            )
            for f in folders
        ]

    def _current_project(self):
        return self._slicer._selector.currentText()

    def _get_reviews(self):
        project = self._current_project()
        print(f"Getting reviews for project {project}")
        self._review_data = ayon_api.get_entity_lists(project_name=project)
        print(f"NEW REVIEWS: {self._review_data}")
        # for r in self._review_data:
        #     print(json.dumps(r, indent=4))

    def _build_folder_type_icons(self, project_name: str) -> dict[str, str]:
        """Build a folderType name → icon name mapping.

        Args:
            project_name: The AYON project name.

        Returns:
            dict mapping folder type name to Material Symbols
            icon name.
        """
        if not project_name:
            return {}
        project_entity = ayon_api.get_project(project_name)
        # print(f"project_entity: {project_entity}")
        if not project_entity:
            return {}
        return {
            ft["name"]: ft["icon"]
            for ft in project_entity.get("folderTypes", [])
        }

    def on_project_changed(self, project_name):
        # print(f"Project changed to {project_name}")
        self._get_reviews()
        self._folder_type_icons = self._build_folder_type_icons(project_name)
        self._model.reset()

    def _on_category_changed(self, category: str):
        self._current_category = category
        self._model.reset()
        # Re-wire the slicer proxy after reset
        self._slicer.set_model(self._model)
