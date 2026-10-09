"""Tests for the version history panel of the Scene Inventory."""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any, Callable, Iterable

import pytest
from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.tools.common_models import UserItem
from ayon_core.tools.common_models.projects import StatusItem
from ayon_core.tools.sceneinventory.models import (
    VersionHistoryItem,
    VersionHistoryModel,
    version_history as version_history_model,
)
from ayon_core.tools.sceneinventory.models.containers import (
    ContainerItem,
    RepresentationInfo,
    VersionItem,
)
from ayon_core.tools.sceneinventory.version_history import (
    AUTHOR_NAME_ROLE,
    IS_LATEST_ROLE,
    IS_LOADED_ROLE,
    NO_SELECTION_TEXT,
    STATUS_COLOR_ROLE,
    STATUS_ICON_ROLE,
    STATUS_NAME_ROLE,
    STATUS_SHORT_ROLE,
    THUMBNAIL_ROLE,
    VERSION_ID_ROLE,
    VersionHistoryWidget,
    _format_relative_date,
)
from ayon_core.tools.sceneinventory.window import SceneInventoryWindow
from ayon_core.ui.components import user_avatars

PROJECT_NAME = "demo"
STATUSES = [
    StatusItem("In progress", "#3498db", "PRG", "play_arrow", "in_progress"),
    StatusItem("Approved", "#00f0b4", "APP", "task_alt", "done"),
]
# Product name -> (folder path, version entities, loaded versions)
PRODUCTS: dict[str, tuple[str, list[dict[str, Any]], list[int]]] = {
    "modelMain": (
        "/assets/characters/hero",
        [
            {
                "version": version,
                "author": author,
                "createdAt": f"2026-09-{10 + version:02d}T09:30:00+00:00",
                "status": status,
                "attrib": {"comment": comment},
                # The first version was published without a thumbnail
                "thumbnailId": f"thumbnail{version}" if version > 1 else None,
            }
            for version, author, status, comment in (
                (1, "roy", "Approved", "Initial blockout"),
                (2, "roy", "Approved", "Fixed topology around the mouth"),
                (3, "libor", "Approved", "UV layout,\nready for lookdev"),
                (4, "roy", "In progress", None),
                (5, "libor", "In progress", "Added teeth and tongue"),
            )
        ],
        [3],
    ),
    "rigMain": (
        "/assets/characters/hero",
        [
            {
                "version": 1,
                "author": "unknown_user",
                "createdAt": "2026-09-20T12:00:00+00:00",
                "status": "Approved",
                "attrib": {},
            },
        ],
        [1],
    ),
}


def _new_id() -> str:
    return uuid.uuid4().hex


class FakeController:
    """Scene inventory controller with sample data instead of a server.

    Implements what the window, the view and the version history need, so
    the tool can be shown without a host or an AYON server.
    """

    def __init__(self) -> None:
        self.server_calls = {"versions": 0, "users": 0}
        self.users_error: Exception | None = None
        # What activity was asked for
        self.activity_calls: list[tuple[str, tuple[str, ...]]] = []
        self.container_items: list[ContainerItem] = []
        self.repre_infos: dict[str, RepresentationInfo] = {}
        self.version_entities: dict[str, list[dict[str, Any]]] = {}
        self.version_ids: dict[tuple[str, int], str] = {}
        self.history_calls: list[tuple[str, str]] = []
        # Thumbnail id -> path to an image
        self.thumbnail_paths: dict[str, str] = {}
        self.thumbnail_calls: list[tuple[str, str, str]] = []
        self.reset_count = 0
        self._history_model = VersionHistoryModel(self)

        for product_name, (folder_path, versions, loaded) in (
            PRODUCTS.items()
        ):
            product_id = _new_id()
            entities = []
            for version in versions:
                entity = dict(version, id=_new_id(), productId=product_id)
                entities.append(entity)
                self.version_ids[(product_name, entity["version"])] = (
                    entity["id"]
                )
            self.version_entities[product_id] = entities
            for version in loaded:
                self.add_container(
                    product_name, product_id, folder_path, version
                )

    def add_container(
        self,
        product_name: str,
        product_id: str,
        folder_path: str,
        version: int,
    ) -> ContainerItem:
        repre_id = str(uuid.uuid4())
        self.repre_infos[repre_id] = RepresentationInfo(
            folder_id=_new_id(),
            folder_path=folder_path,
            product_id=product_id,
            product_name=product_name,
            product_type="model",
            product_type_icon=None,
            product_group=None,
            version_id=self.version_ids[(product_name, version)],
            representation_name="abc",
        )
        container_item = ContainerItem(
            representation_id=repre_id,
            loader_name="ReferenceLoader",
            namespace=f"hero_{product_name}_{version:02d}",
            object_name=f"hero_{product_name}_{version:02d}_CON",
            item_id=_new_id(),
            project_name=PROJECT_NAME,
            version_locked=False,
        )
        self.container_items.append(container_item)
        return container_item

    def product_id(self, product_name: str) -> str:
        return next(
            info.product_id
            for info in self.repre_infos.values()
            if info.product_name == product_name
        )

    def item_ids(self, product_name: str) -> list[str]:
        return [
            item.item_id
            for item in self.container_items
            if self.repre_infos[item.representation_id].product_name
            == product_name
        ]

    # Controller interface
    def get_window_subtitle(self) -> str:
        return "fakehost"

    def reset(self) -> None:
        self.reset_count += 1
        self._history_model.reset()

    def get_container_items(self) -> list[ContainerItem]:
        return list(self.container_items)

    def get_container_items_by_id(
        self, item_ids: Iterable[str]
    ) -> dict[str, ContainerItem | None]:
        items_by_id = {item.item_id: item for item in self.container_items}
        return {item_id: items_by_id.get(item_id) for item_id in item_ids}

    def get_representation_info_items(
        self, project_name: str, representation_ids: Iterable[str]
    ) -> dict[str, RepresentationInfo]:
        return {
            repre_id: self.repre_infos.get(
                repre_id, RepresentationInfo.new_invalid()
            )
            for repre_id in representation_ids
        }

    def get_version_items(
        self, project_name: str, product_ids: Iterable[str]
    ) -> dict[str, dict[str, VersionItem]]:
        output = {}
        for product_id in product_ids:
            entities = self.version_entities[product_id]
            last_version = max(entity["version"] for entity in entities)
            output[product_id] = {
                entity["id"]: VersionItem.from_entity(
                    entity, entity["version"] == last_version, False
                )
                for entity in entities
            }
        return output

    def get_project_status_items(
        self, project_name: str | None = None
    ) -> list[StatusItem]:
        return list(STATUSES)

    def is_sitesync_enabled(self) -> bool:
        return False

    def get_sites_information(self, project_name: str) -> dict[str, Any]:
        return {
            "active_site": None,
            "active_site_provider": None,
            "remote_site": None,
            "remote_site_provider": None,
        }

    def get_site_provider_icons(self) -> dict[str, Any]:
        return {}

    def get_representations_site_progress(
        self, project_name: str, representation_ids: Iterable[str]
    ) -> dict[str, dict[str, int]]:
        return {
            repre_id: {"active_site": 0, "remote_site": 0}
            for repre_id in representation_ids
        }

    def get_version_history_contexts(self, item_ids: Iterable[str]):
        return self._history_model.get_contexts(item_ids)

    def get_version_history_items(
        self, project_name: str, product_id: str
    ) -> list[VersionHistoryItem]:
        self.history_calls.append((project_name, product_id))
        return self._history_model.get_items(project_name, product_id)

    def get_version_thumbnail_path(
        self, project_name: str, version_id: str, thumbnail_id: str
    ) -> str:
        self.thumbnail_calls.append((project_name, version_id, thumbnail_id))
        return self.thumbnail_paths.get(thumbnail_id, "")

    def get_activity_items(
        self, project_name: str, entity_ids: list[str], limit: int = 50
    ) -> list:
        self.activity_calls.append((project_name, tuple(entity_ids)))
        return []

    def get_user_items(self, project_name: str) -> list[UserItem]:
        self.server_calls["users"] += 1
        if self.users_error is not None:
            raise self.users_error
        return [
            UserItem("roy", "Roy Nieterau", None, None, True),
            UserItem("libor", None, None, None, True),
        ]

    def get_user_avatar_path(self, username: str) -> None:
        return None


@pytest.fixture
def app() -> QtWidgets.QApplication:
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture(autouse=True)
def no_avatars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avatars would be downloaded from the server."""
    monkeypatch.setattr(
        user_avatars, "_fetch_avatar_file", lambda user_name: ""
    )
    monkeypatch.setattr(
        "ayon_core.tools.common_models.users.get_user_avatar_path",
        lambda username: None,
    )


@pytest.fixture
def controller(monkeypatch: pytest.MonkeyPatch) -> FakeController:
    controller = FakeController()

    def get_versions(project_name: str, product_ids=None, **kwargs: Any):
        controller.server_calls["versions"] += 1
        for product_id in product_ids:
            yield from controller.version_entities[product_id]

    monkeypatch.setattr(
        version_history_model.ayon_api, "get_versions", get_versions
    )
    return controller


def _wait_for(
    app: QtWidgets.QApplication,
    condition: Callable[[], bool],
    timeout: float = 5.0,
) -> None:
    """Process events until background tasks made the condition true."""
    end = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > end:
            raise AssertionError("Timed out waiting for the condition")
        app.processEvents()
        time.sleep(0.005)


def _rows(widget: VersionHistoryWidget) -> list[list[Any]]:
    model = widget._versions_model
    return [
        [
            model.index(row, col).data()
            for col in range(model.columnCount())
        ]
        for row in range(model.rowCount())
    ]


def test_items_are_newest_first_with_latest_and_hero(controller):
    product_id = controller.product_id("modelMain")
    controller.version_entities[product_id].append({
        "id": "hero",
        "productId": product_id,
        "version": -3,
        "author": "roy",
        "createdAt": "2026-09-13T10:00:00+00:00",
        "status": "Approved",
        "attrib": {"comment": "Hero"},
    })
    model = VersionHistoryModel(controller)

    items = model.get_items(PROJECT_NAME, product_id)

    assert [item.version for item in items] == [-3, 5, 4, 3, 2, 1]
    assert [item.is_latest for item in items] == [
        False, True, False, False, False, False
    ]
    assert items[0].is_hero and not items[1].is_hero
    # Full name is used when filled, username otherwise
    assert [item.author for item in items[1:3]] == ["libor", "Roy Nieterau"]
    # Missing comment is an empty string
    assert [item.comment for item in items[1:3]] == [
        "Added teeth and tongue", ""
    ]


def test_items_and_users_are_cached_until_reset(controller):
    model = VersionHistoryModel(controller)
    product_id = controller.product_id("modelMain")

    model.get_items(PROJECT_NAME, product_id)
    model.get_items(PROJECT_NAME, product_id)
    model.get_items(PROJECT_NAME, controller.product_id("rigMain"))
    assert controller.server_calls == {"versions": 2, "users": 1}

    model.reset()
    model.get_items(PROJECT_NAME, product_id)
    assert controller.server_calls == {"versions": 3, "users": 2}


def test_username_is_used_when_users_can_not_be_fetched(
    controller, monkeypatch
):
    controller.users_error = RuntimeError("Forbidden")
    items = VersionHistoryModel(controller).get_items(
        PROJECT_NAME, controller.product_id("modelMain")
    )
    assert items[0].author == "libor"


def test_contexts_merge_containers_of_a_product(controller):
    product_id = controller.product_id("modelMain")
    controller.add_container(
        "modelMain", product_id, "/assets/characters/hero", 5
    )
    # Container of a representation that does not exist anymore
    invalid_item = controller.add_container(
        "rigMain", controller.product_id("rigMain"), "", 1
    )
    item_ids = controller.item_ids("modelMain")
    controller.repre_infos.pop(invalid_item.representation_id)
    model = VersionHistoryModel(controller)

    contexts = model.get_contexts(
        item_ids + [invalid_item.item_id, "missing"]
    )

    assert len(contexts) == 1
    context = contexts[0]
    assert (context.project_name, context.product_id) == (
        PROJECT_NAME, product_id
    )
    assert context.product_name == "modelMain"
    assert context.folder_path == "/assets/characters/hero"
    assert context.loaded_version_ids == {
        controller.version_ids[("modelMain", 3)],
        controller.version_ids[("modelMain", 5)],
    }
    assert model.get_contexts([]) == []


def test_widget_lists_versions_and_marks_loaded_and_latest(app, controller):
    widget = VersionHistoryWidget(controller)
    widget.resize(900, 240)
    widget.show()
    assert widget._message_label.text() == NO_SELECTION_TEXT

    widget.set_selected_item_ids(controller.item_ids("modelMain"))
    _wait_for(app, lambda: widget._versions_model.rowCount() > 0)

    rows = _rows(widget)
    assert [row[widget.version_col] for row in rows] == [
        "v005", "v004", "v003", "v002", "v001"
    ]
    assert rows[0][widget.author_col] == "libor"
    assert rows[1][widget.author_col] == "Roy Nieterau"
    assert rows[0][widget.comment_col] == "Added teeth and tongue"
    # Multiline comment is displayed on a single line
    assert rows[2][widget.comment_col] == "UV layout, ready for lookdev"
    model = widget._versions_model
    flags = [
        (
            model.index(row, widget.version_col).data(IS_LOADED_ROLE),
            model.index(row, widget.version_col).data(IS_LATEST_ROLE),
        )
        for row in range(model.rowCount())
    ]
    assert flags == [
        (False, True),
        (False, False),
        (True, False),
        (False, False),
        (False, False),
    ]
    assert "modelMain" in widget._title_label.text()
    assert "2 newer than loaded" in widget._summary_label.text()

    # Activity of the loaded version is shown by default
    loaded_id = controller.version_ids[("modelMain", 3)]
    assert widget.get_selected_version_id() == loaded_id
    _wait_for(app, lambda: bool(controller.activity_calls))
    assert controller.activity_calls == [(PROJECT_NAME, (loaded_id,))]

    # ... and follows the version selected in the list
    widget._versions_view.setCurrentIndex(model.index(0, 0))
    latest_id = model.index(0, widget.version_col).data(VERSION_ID_ROLE)
    assert latest_id == controller.version_ids[("modelMain", 5)]
    _wait_for(app, lambda: len(controller.activity_calls) == 2)
    assert controller.activity_calls[-1] == (PROJECT_NAME, (latest_id,))
    widget.close()


def test_widget_needs_a_single_product(app, controller):
    widget = VersionHistoryWidget(controller)
    widget.show()

    widget.set_selected_item_ids(
        controller.item_ids("modelMain") + controller.item_ids("rigMain")
    )
    assert "2 products selected" in widget._message_label.text()
    assert widget._pages.currentIndex() == 0

    widget.set_selected_item_ids(controller.item_ids("rigMain"))
    _wait_for(app, lambda: widget._versions_model.rowCount() > 0)
    assert "up to date" in widget._summary_label.text()

    widget.set_selected_item_ids([])
    assert widget._message_label.text() == NO_SELECTION_TEXT
    assert widget._versions_model.rowCount() == 0
    widget.close()


def test_widget_remarks_loaded_version_without_fetching(app, controller):
    widget = VersionHistoryWidget(controller)
    widget.show()
    widget.set_selected_item_ids(controller.item_ids("modelMain"))
    _wait_for(app, lambda: widget._versions_model.rowCount() > 0)
    assert len(controller.history_calls) == 1

    # The container was updated to the latest version
    container_item = controller.container_items[0]
    controller.repre_infos[container_item.representation_id].version_id = (
        controller.version_ids[("modelMain", 5)]
    )
    widget.set_selected_item_ids(controller.item_ids("modelMain"))

    assert len(controller.history_calls) == 1
    index = widget._versions_model.index(0, widget.version_col)
    assert index.data(IS_LOADED_ROLE) is True
    assert "up to date" in widget._summary_label.text()
    widget.close()


def test_widget_status_author_and_date_cells(app, controller):
    widget = VersionHistoryWidget(controller)
    widget.resize(900, 240)
    widget.show()
    widget.set_selected_item_ids(controller.item_ids("modelMain"))
    _wait_for(app, lambda: widget._versions_model.rowCount() > 0)
    model = widget._versions_model

    # Status has what the shared status delegate needs to draw the icon
    #   and to fall back to the short name in a narrow column
    status_index = model.index(0, widget.status_col)
    assert status_index.data(STATUS_NAME_ROLE) == "In progress"
    assert status_index.data(STATUS_SHORT_ROLE) == "PRG"
    assert status_index.data(STATUS_COLOR_ROLE) == "#3498db"
    assert isinstance(status_index.data(STATUS_ICON_ROLE), QtGui.QIcon)
    assert widget._versions_view.itemDelegateForColumn(
        widget.status_col
    ) is widget._status_delegate

    # Avatar is looked up by username, full name is displayed
    author_index = model.index(1, widget.author_col)
    assert author_index.data(AUTHOR_NAME_ROLE) == "roy"
    assert author_index.data() == "Roy Nieterau"

    # Date is relative with the exact date in the tooltip
    date_index = model.index(0, widget.date_col)
    assert date_index.data() == _format_relative_date(
        "2026-09-15T09:30:00+00:00"
    )
    assert date_index.data(QtCore.Qt.ToolTipRole).startswith("2026-09-15")

    # Painting with the custom delegates does not fail
    assert not widget.grab().isNull()
    widget.close()


def test_relative_date_format():
    now = datetime(2026, 10, 5, 12, 0, 0)

    def fmt(date: datetime) -> str:
        return _format_relative_date(date.isoformat(), now=now)

    assert fmt(datetime(2026, 10, 5, 11, 59, 55)) == "just now"
    assert fmt(datetime(2026, 10, 5, 11, 38, 0)) == "22 minutes ago"
    assert fmt(datetime(2026, 10, 5, 9, 55, 0)) == "2:05 hours ago"
    assert fmt(datetime(2026, 10, 4, 11, 0, 0)) == "yesterday"
    assert fmt(datetime(2026, 10, 3, 11, 0, 0)) == "2 days ago"
    assert fmt(datetime(2026, 9, 5, 12, 0, 0)) == "30 days ago"
    assert fmt(datetime(2026, 8, 1, 12, 0, 0)) == "Aug 01 2026"
    assert _format_relative_date("not a date") == "not a date"
    assert _format_relative_date("") == ""


def test_widget_loads_thumbnails_of_versions(app, controller, tmp_path):
    image_path = tmp_path / "thumbnail.png"
    pixmap = QtGui.QPixmap(32, 18)
    pixmap.fill(QtGui.QColor("red"))
    assert pixmap.save(str(image_path))
    # Thumbnail of the latest version can not be downloaded
    controller.thumbnail_paths = {
        f"thumbnail{version}": str(image_path) for version in (2, 3, 4)
    }
    widget = VersionHistoryWidget(controller)
    widget.show()
    widget.set_selected_item_ids(controller.item_ids("modelMain"))
    model = widget._versions_model

    def _thumbnails() -> list[bool]:
        return [
            model.index(row, widget.thumbnail_col).data(THUMBNAIL_ROLE)
            is not None
            for row in range(model.rowCount())
        ]

    _wait_for(app, lambda: sum(_thumbnails()) == 3)
    assert _thumbnails() == [False, True, True, True, False]
    # Nothing is asked for a version without a thumbnail
    assert sorted(call[2] for call in controller.thumbnail_calls) == [
        "thumbnail2", "thumbnail3", "thumbnail4", "thumbnail5"
    ]
    assert not widget.grab().isNull()
    widget.close()


def test_widget_fetches_nothing_while_hidden(app, controller):
    widget = VersionHistoryWidget(controller)

    widget.set_selected_item_ids(controller.item_ids("modelMain"))
    app.processEvents()
    assert controller.history_calls == []

    widget.show()
    _wait_for(app, lambda: widget._versions_model.rowCount() > 0)
    assert len(controller.history_calls) == 1
    widget.close()


def test_window_history_is_hidden_by_default_and_keeps_width(
    app, controller
):
    window = SceneInventoryWindow(controller=controller)
    window.show()
    window.refresh()
    app.processEvents()
    size = window.size()
    history_widget = window._history_widget
    assert not history_widget.isVisible()

    # Select the first product while the history is hidden
    view = window._view
    index = view.model().index(0, 0)
    view.selectionModel().select(
        index,
        QtCore.QItemSelectionModel.ClearAndSelect
        | QtCore.QItemSelectionModel.Rows,
    )
    app.processEvents()
    assert controller.history_calls == []

    history_button = window._history_button
    assert history_button.icon().cacheKey() == window._history_icon.cacheKey()
    window._history_button.setChecked(True)
    assert (
        history_button.icon().cacheKey()
        == window._history_checked_icon.cacheKey()
    )
    assert history_widget.isVisible()
    _wait_for(app, lambda: history_widget._versions_model.rowCount() > 0)
    assert window.size() == size
    assert history_widget.height() >= 150

    # Selection is restored with new container ids after a refresh
    window.refresh()
    _wait_for(app, lambda: history_widget._versions_model.rowCount() > 0)
    assert history_widget._pages.currentIndex() == 1

    view.selectionModel().clearSelection()
    assert history_widget._message_label.text() == NO_SELECTION_TEXT

    window._history_button.setChecked(False)
    # The icon is not highlighted anymore, even with focus on the button
    assert history_button.icon().cacheKey() == window._history_icon.cacheKey()
    assert not history_widget.isVisible()
    assert window.size() == size
    window.close()


def test_controller_provides_the_activity_of_versions(monkeypatch):
    from ayon_core.tools.common_models import ActivitiesModel, UsersModel
    from ayon_core.tools.sceneinventory.control import (
        SceneInventoryController,
    )

    calls = []
    monkeypatch.setattr(
        ActivitiesModel,
        "get_activity_items",
        lambda self, *args: calls.append(("activities", args)) or [],
    )
    monkeypatch.setattr(
        UsersModel,
        "get_user_items",
        lambda self, *args: calls.append(("users", args)) or [],
    )
    # A host is not needed for what the activity widget asks for
    controller = SceneInventoryController(host=object())

    assert controller.get_activity_items(PROJECT_NAME, ["version_id"]) == []
    assert controller.get_user_items(PROJECT_NAME) == []
    assert calls == [
        ("activities", (PROJECT_NAME, ["version_id"], 50)),
        ("users", (PROJECT_NAME,)),
    ]
    assert callable(controller.get_project_status_items)


def test_controller_uses_the_shared_thumbnail_and_avatar_caches(monkeypatch):
    from ayon_core.tools.sceneinventory.control import (
        SceneInventoryController,
    )

    calls = []

    def get_thumbnail_path(*args: str):
        calls.append(args)
        return "/cache/thumbnail.png"

    monkeypatch.setattr(
        "ayon_core.tools.common_models.thumbnails.get_thumbnail_path",
        get_thumbnail_path,
    )
    monkeypatch.setattr(
        "ayon_core.tools.common_models.users.get_user_avatar_path",
        lambda username: f"/avatars/{username}.png",
    )
    controller = SceneInventoryController(host=object())

    assert (
        controller.get_version_thumbnail_path(PROJECT_NAME, "v1", "t1")
        == "/cache/thumbnail.png"
    )
    assert calls == [(PROJECT_NAME, "version", "v1", "t1")]
    assert controller.get_user_avatar_path("roy") == "/avatars/roy.png"
