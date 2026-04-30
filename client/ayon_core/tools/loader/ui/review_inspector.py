from __future__ import annotations

from ayon_ui_qt.components.container import AYContainer
from ayon_ui_qt.components.layouts import AYHBoxLayout
from ayon_ui_qt.components.label import AYLabel
from ayon_ui_qt.components.buttons import AYButton
from ayon_ui_qt.components.entity_thumbnail import AYEntityThumbnail
from ayon_ui_qt.components.task_queue import AsyncTask, get_task_queue
from ayon_ui_qt.components.table_view import AYTableView
from ayon_ui_qt.image_cache import ImageCache
from qtpy import QtCore, QtWidgets, QtGui, shiboken

from ayon_core.tools.utils import get_qt_icon

from ._review_thumbnails import _thumbnail_loader


def _str_wrap(text: str) -> str:
    # Insert a zero-width space after common path separators so long
    # paths wrap inside a word-wrapping QLabel.
    for ch in ("/", "\\", "_", "-", "."):
        text = text.replace(ch, ch + "\u200b")
    return text


class ReviewInspector(AYContainer):
    """A placeholder widget for the review inspector panel."""

    def __init__(self, *args, controller=None, **kwargs):
        super().__init__(
            *args,
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.Low,
            layout_margin=10,
            layout_spacing=10,
            **kwargs,
        )
        self._layout.setAlignment(QtCore.Qt.AlignTop)
        self.setMinimumWidth(300)

        self._controller = controller
        self._view: QtWidgets.QAbstractItemView | None = None
        self._current_thumb_key: str = ""
        # Use a dict as an ordered set to track the currently selected indices
        self._current_selection: dict[QtCore.QModelIndex, None] = {}

        self._build()

    def _build(self) -> None:
        """Build the inspector UI. This is a placeholder method."""

        # top bar with path and close button
        top_bar = AYHBoxLayout(margin=0, spacing=5)
        self._path_label = AYLabel(
            "",
            dim=True,
            elide_mode=QtCore.Qt.TextElideMode.ElideMiddle,
            rel_text_size=-1,
            copy_text=True,
        )
        self._close_btn = AYButton(
            variant=AYButton.Variants.Nav_Small, icon="close", icon_size=14
        )
        self._close_btn.clicked.connect(self._on_close)
        top_bar.addWidget(
            self._path_label, stretch=10, alignment=QtCore.Qt.AlignLeft
        )
        top_bar.addStretch()
        top_bar.addWidget(self._close_btn)
        self.add_layout(top_bar)

        # thumbnail
        self._thumbnail = AYEntityThumbnail(
            variant=AYEntityThumbnail.Variants.Entity_Card,
            size=(280, 160),
        )
        thumb_wrapper = AYHBoxLayout(margin=0, spacing=0)
        thumb_wrapper.setAlignment(QtCore.Qt.AlignCenter)
        thumb_wrapper.addWidget(self._thumbnail)
        self.add_layout(thumb_wrapper)

        # Version info
        self.add_widget(
            AYLabel(
                "Version Info",
                variant=AYLabel.Variants.Default,
                rel_text_size=1,
            )
        )
        self.info_lyt = AYContainer(
            layout=AYContainer.Layout.Form,
            variant=AYContainer.Variants.Low_Framed_Thin,
            layout_margin=10,
            layout_spacing=(20, 20),
        )
        self.info_lyt.set_label_alignment(QtCore.Qt.AlignRight)
        self.add_widget(self.info_lyt)
        # product name
        self._product_value = AYLabel("-")
        self.info_lyt.add_row(
            AYLabel("Product:", dim=True), self._product_value
        )
        # version name
        self._version_value = AYLabel("-")
        self.info_lyt.add_row(
            AYLabel("Version:", dim=True), self._version_value
        )
        # comment
        self._comment_value = AYLabel("-", copy_text=True)
        self._comment_value.setWordWrap(True)
        cmt_wrapper = AYContainer(
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Low,
            layout_margin=0,
            layout_spacing=0,
        )
        cmt_wrapper.add_widget(self._comment_value, stretch=1)
        self.info_lyt.add_row(AYLabel("Comment:", dim=True), cmt_wrapper)
        # created
        self._created_value = AYLabel("-")
        self.info_lyt.add_row(
            AYLabel("Created:", dim=True), self._created_value
        )
        # source
        self._source_value = AYLabel("-", copy_text=True)
        self._source_value.setWordWrap(True)
        src_wrapper = AYContainer(
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Low,
            layout_margin=0,
            layout_spacing=0,
        )
        src_wrapper.add_widget(self._source_value, stretch=1)
        self.info_lyt.add_row(AYLabel("Source:", dim=True), src_wrapper)

        # representations
        self.add_widget(
            AYLabel(
                "Representations",
                variant=AYLabel.Variants.Default,
                rel_text_size=1,
            )
        )
        self._representations = Representations()
        self.add_widget(self._representations)

    def set_view(self, view: QtWidgets.QAbstractItemView) -> None:
        """Set the view for the inspector."""
        print(f"Setting inspector view: {view}")
        self._view = view
        self._view.activated.connect(self._on_activated)
        self._view.selection_changed.connect(self._on_selection_changed)

    def _on_activated(self, index: QtCore.QModelIndex) -> None:
        """Activation is typically when the user double-clicks on an item.
        We want to show the inspector in this case if it's not visible.
        """
        self.show()
        self._update()

    def _on_selection_changed(
        self,
        selected: QtCore.QItemSelection,
        deselected: QtCore.QItemSelection,
    ) -> None:
        """Record the selection changes and update the inspector.

        Args:
            selected (QtCore.QItemSelection): The selected items.
            deselected (QtCore.QItemSelection): The deselected items.
        """
        # NOTE: only consider column 0 as we select entire rows in all views
        for idx in selected.indexes():
            if idx.column() == 0:
                self._current_selection[idx] = None
        for idx in deselected.indexes():
            if idx.column() == 0:
                self._current_selection.pop(idx, None)
        self._update()

    def _update(self) -> None:
        """Update the inspector with the current selection, if it is visible."""
        if not self.isVisible():
            return

        index = next(iter(self._current_selection), QtCore.QModelIndex())
        data = index.data(QtCore.Qt.ItemDataRole.UserRole) or {}
        n_sel = len(self._current_selection)
        single = n_sel <= 1
        default = "-" if single else f"{n_sel} items selected"

        # Folder rows have no version data — clear and bail out.
        if data.get("entityType", "") == "Folder":
            self._representations.set_items([])
            return

        # print(f"Updating inspector with data: {data}")
        self._path_label.setText(
            data.get("path", default) if single else default
        )
        self._product_value.setText(
            data.get("productName", default) if single else default
        )
        self._version_value.setText(
            data.get("version", default) if single else default
        )
        self._comment_value.setText(
            data.get("comment", default) or default if single else default
        )
        self._created_value.setText(
            data.get("createdAt", default) if single else default
        )
        self._source_value.setText(
            _str_wrap(data.get("source", default) if single else default)
        )

        thumbnail_id = data.get("thumbnailId", "")
        version_id = data.get("_version_id") or data.get("id", "")
        project_name = data.get("project_name", "")
        if thumbnail_id and version_id and project_name:
            key = f"{project_name}/{version_id}/{thumbnail_id}"
            self._load_thumbnail(key)
        else:
            self._current_thumb_key = ""
            self._thumbnail.set_thumbnail("")

        # Fetch and display representations for this version.
        if self._controller and project_name and version_id:
            repre_items = self._controller.get_representation_items(
                project_name, [version_id]
            )
            self._representations.set_items(repre_items)
        else:
            self._representations.set_items([])

    def _load_thumbnail(self, key: str) -> None:
        """Load and display the thumbnail for *key*.

        Serves from :class:`ImageCache` synchronously when the image is
        already cached, otherwise enqueues an async fetch at priority 1
        (higher than the table's eager pre-fetch at priority 2).

        Args:
            key: Cache key in the form
                ``"<project_name>/<version_id>/<thumbnail_id>"``.
        """
        self._current_thumb_key = key
        ic = ImageCache.get_instance()
        cached_path = ic.get_path(key) if key else None
        if cached_path:
            self._thumbnail.set_thumbnail(cached_path)
            return

        inspector = self

        def _on_loaded(fpath: str) -> None:
            if not shiboken.isValid(inspector):
                return
            if inspector._current_thumb_key != key:
                return
            inspector._thumbnail.set_thumbnail(fpath or "")

        get_task_queue().enqueue(
            AsyncTask(
                name=f"inspector_thumb_{key}",
                function=lambda: _thumbnail_loader(key),
                callback=_on_loaded,
                priority=1,
                cancellable=True,
            )
        )

    def _on_close(self) -> None:
        """Hide the inspector."""
        self.hide()


class Representations(AYContainer):
    """Widget displaying the representations for an inspected version."""

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.Low_Framed_Thin,
            layout_margin=2,
            **kwargs,
        )
        self._layout.setAlignment(QtCore.Qt.AlignTop)
        self._table: AYTableView = AYTableView(
            variant=AYTableView.Variants.Low,
        )
        self._model = QtGui.QStandardItemModel()
        self._model.setHorizontalHeaderLabels(["Name", "Folder", "Product"])
        self._table.setModel(self._model)

        self.add_widget(self._table)

    def set_items(self, repre_items: list) -> None:
        """Populate the table from a list of RepreItem.

        Args:
            repre_items: List of
                :class:`~ayon_core.tools.loader.abstract.RepreItem`
                objects to display.
        """
        self._model.removeRows(0, self._model.rowCount())
        for repre in repre_items:
            # print(repre.to_data())

            name_item = QtGui.QStandardItem(repre.representation_name)
            name_item.setEditable(False)
            icon = get_qt_icon(repre.representation_icon)
            if icon is not None:
                name_item.setIcon(icon)

            folder_item = QtGui.QStandardItem(repre.folder_label)
            folder_item.setEditable(False)

            product_item = QtGui.QStandardItem(repre.product_name)
            product_item.setEditable(False)

            self._model.appendRow([name_item, folder_item, product_item])
