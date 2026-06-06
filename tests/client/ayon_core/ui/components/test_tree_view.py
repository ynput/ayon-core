"""Visual regression tests for AYTreeView."""

from __future__ import annotations

from qtpy.QtWidgets import QWidget

from widget_test import WidgetTest
from ayon_core.ui.components.tree_view import AYTreeView
from ayon_core.ui.components.tree_model import LazyTreeModel, TreeNode
from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.label import AYLabel


# ---------------------------------------------------------------------------
# Fake tree data
# ---------------------------------------------------------------------------

_TREE_DATA: dict[str | None, list[TreeNode]] = {
    None: [
        TreeNode(id="assets",  label="Assets",  has_children=True,  icon="folder",      icon_color="#f4c430"),
        TreeNode(id="shots",   label="Shots",   has_children=True,  icon="movie",       icon_color="#74b9ff"),
        TreeNode(id="renders", label="Renders", has_children=False, icon="photo_library",icon_color="#a29bfe"),
    ],
    "assets": [
        TreeNode(id="chars",  label="Characters", has_children=True,  icon="person",    icon_color="#fd79a8"),
        TreeNode(id="props",  label="Props",      has_children=False, icon="category",  icon_color="#fdcb6e"),
    ],
    "shots": [
        TreeNode(id="sq010", label="sq010", has_children=True,  icon="local_movies", icon_color="#55efc4"),
        TreeNode(id="sq020", label="sq020", has_children=False, icon="local_movies", icon_color="#55efc4"),
    ],
    "chars": [
        TreeNode(id="hero",     label="hero",     has_children=False, icon="person"),
        TreeNode(id="villain",  label="villain",  has_children=False, icon="person"),
    ],
    "sq010": [
        TreeNode(id="sh010", label="sh010", has_children=False, icon="videocam"),
        TreeNode(id="sh020", label="sh020", has_children=False, icon="videocam"),
    ],
}


def _fetch(parent_id: str | None) -> list[TreeNode]:
    return _TREE_DATA.get(parent_id, [])


class TreeViewTest(WidgetTest):
    """Tests AYTreeView across Default, Low, and High variants with lazy data."""

    size = (700, 400)
    tolerance = 0.0

    def build(self) -> QWidget:
        root = AYContainer(
            layout=AYContainer.Layout.HBox,
            layout_margin=20,
            layout_spacing=12,
        )

        self._views: list[AYTreeView] = []
        # Keep a strong reference to each model; they have no QObject
        # parent so Python's GC would otherwise collect them while Qt
        # still holds raw pointers via QModelIndex.internalPointer().
        self._models: list[LazyTreeModel] = []
        for variant in AYTreeView.Variants:
            col = AYContainer(
                layout=AYContainer.Layout.VBox,
                layout_margin=0,
                layout_spacing=4,
            )
            col.add_widget(AYLabel(f"Variant: {variant.name}"))
            model = LazyTreeModel(fetch_children=_fetch, no_async=True)
            self._models.append(model)
            view = AYTreeView(variant=variant)
            view.setModel(model)
            view.expandAll()
            self._views.append(view)
            col.add_widget(view, stretch=1)
            root.add_widget(col, stretch=1)

        return root

    def collapse_all(self) -> None:
        """Collapse all nodes to show unexpanded root items."""
        for view in self._views:
            view.collapseAll()

    def wait_loaded(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        """Flush pending paint events; data was loaded synchronously."""
        from qtpy.QtWidgets import QApplication
        QApplication.processEvents()

    def steps(self):
        return [self.collapse_all]
