"""Tests for the recent actions recorded and re-run by the actions model."""

from __future__ import annotations

import copy
import time
import uuid
from typing import Any, Optional

import pytest

import ayon_api

from ayon_core.lib.icon_definitions import MaterialSymbolsIcon
from ayon_core.tools.launcher.abstract import (
    RECENT_ACTIONS_MAX,
    WebactionContext,
)
from ayon_core.tools.launcher.models import ActionsModel
from ayon_core.tools.launcher.models.recent_actions import (
    PREFERENCES_ITEM,
    PREFERENCES_NAME,
)


class FakeController:
    """Just what the actions model asks of the launcher backend."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def emit_event(self, topic, data=None, source=None) -> None:
        self.events.append((topic, data))

    def get_project_settings(self, project_name) -> dict[str, Any]:
        return {}

    def get_project_entity(self, project_name) -> dict[str, Any]:
        return {
            "name": project_name,
            "code": "PRJ",
            "folderTypes": [{"name": "Asset", "icon": "category"}],
            "taskTypes": [
                {"name": "Modeling", "icon": "language", "color": "#ff0000"}
            ],
        }

    def get_folder_entity(self, project_name, folder_id) -> dict[str, Any]:
        return {"path": f"/{folder_id}", "folderType": "Asset"}

    def get_task_entity(self, project_name, task_id) -> dict[str, Any]:
        return {"name": f"name_{task_id}", "taskType": "Modeling"}


class FakeAction:
    """Discovered local action."""

    label = "Maya"
    order = 0
    icon = MaterialSymbolsIcon("brush")

    def __init__(self) -> None:
        self.compatible = True
        self.failing = False
        self.processed = []

    def is_compatible(self, selection) -> bool:
        return self.compatible

    def process(self, selection) -> None:
        if self.failing:
            raise RuntimeError("Failed to launch")
        self.processed.append(selection)


class Response:
    def __init__(self, status_code: int, data: Optional[dict] = None):
        self.status_code = status_code
        self.status = status_code
        self.data = data or {}
        self.ok = 200 <= status_code < 300
        self.detail = ""

    def raise_for_status(self) -> None:
        if not self.ok:
            raise RuntimeError(self.status_code)


@pytest.fixture
def server(monkeypatch) -> dict[str, Any]:
    """In memory stand-in for the preferences API of AYON server.

    Global preferences of the current user by key, in 'preferences'. A
    'status_code' makes every request answer with it, e.g. 404 of a
    server without the preferences API. Requests are counted in
    'requests'. Each test gets its own server url, whether a server has
    the API is remembered by its url.
    """
    state = {"preferences": {}, "status_code": None, "requests": 0}

    def raw_get(endpoint, **kwargs):
        state["requests"] += 1
        if state["status_code"]:
            return Response(state["status_code"])
        return Response(200, {"preferences": [
            {"key": key, "data": copy.deepcopy(data)}
            for key, data in state["preferences"].items()
        ]})

    def raw_patch(endpoint, **kwargs):
        state["requests"] += 1
        if state["status_code"]:
            return Response(state["status_code"])
        key = endpoint.split("/", 1)[1]
        stored = state["preferences"].setdefault(key, {})
        stored.update(copy.deepcopy(kwargs["json"]))
        return Response(204)

    server_url = f"http://ayon-{uuid.uuid4().hex}"
    monkeypatch.setattr(ayon_api, "raw_get", raw_get)
    monkeypatch.setattr(ayon_api, "raw_patch", raw_patch)
    monkeypatch.setattr(ayon_api, "get_base_url", lambda: server_url)
    return state


class Webactions:
    """Webactions of the server, how they are listed and what they answer.

    Endpoints of executed webactions are in 'executed'.
    """

    def __init__(self) -> None:
        self.addon_version = "1.0.0"
        self.response_type = "simple"
        self.executed: list[str] = []

    def post(self, endpoint, **kwargs) -> Response:
        return Response(200, {"actions": [{
            "identifier": "publish",
            "label": "Publish",
            "groupLabel": None,
            "order": 0,
            "icon": {"type": "material-symbols", "name": "publish"},
            "addonName": "review",
            "addonVersion": self.addon_version,
        }]})

    def raw_post(self, endpoint, **kwargs) -> Response:
        self.executed.append(endpoint)
        payload = {}
        if self.response_type == "form":
            payload = {
                "title": "Publish",
                "fields": [],
                "submit_label": "Submit",
                "submit_icon": None,
                "cancel_label": "Cancel",
                "cancel_icon": None,
            }
        return Response(200, {
            "type": self.response_type,
            "success": True,
            "message": None,
            "payload": payload,
        })


@pytest.fixture
def webactions(monkeypatch) -> Webactions:
    webactions = Webactions()
    monkeypatch.setattr(ayon_api, "post", webactions.post)
    monkeypatch.setattr(ayon_api, "raw_post", webactions.raw_post)
    monkeypatch.setattr(
        ayon_api,
        "get_folder_by_id",
        lambda project_name, folder_id, **kwargs: {
            "id": folder_id, "folderType": "Asset"
        },
    )
    return webactions


def stored_items(server) -> list[dict[str, Any]]:
    return server["preferences"][PREFERENCES_NAME][PREFERENCES_ITEM]


@pytest.fixture
def controller() -> FakeController:
    return FakeController()


@pytest.fixture
def maya() -> FakeAction:
    return FakeAction()


def create_model(controller: FakeController, action: FakeAction):
    model = ActionsModel(controller)
    # As if discovered
    model._actions = {"maya": action}
    return model


@pytest.fixture
def model(controller, server, maya) -> ActionsModel:
    return create_model(controller, maya)


def wait_idle(model: ActionsModel, timeout: float = 5.0) -> None:
    """Wait for the recording worker to have nothing left to do."""
    history = model._recent_actions
    end = time.time() + timeout
    while time.time() < end:
        worker = history._worker
        if (
            not history._queued_items
            and not history._save_requested
            and (worker is None or not worker.is_alive())
        ):
            return
        time.sleep(0.005)
    raise AssertionError("Recent actions worker did not finish.")


def trigger(model, folder_id="f1", task_id=None, workfile_id=None) -> None:
    model.trigger_action("maya", "project", folder_id, task_id, workfile_id)
    wait_idle(model)


def trigger_webaction(model) -> None:
    # The UI lists the actions of the context before one is triggered
    (item,) = [
        item
        for item in model.get_action_items("project", "f1", None, None)
        if item.action_type == "webaction"
    ]
    model.trigger_webaction(
        WebactionContext(
            identifier=item.identifier,
            project_name="project",
            folder_id="f1",
            task_id=None,
            workfile_id=None,
            addon_name=item.addon_name,
            addon_version=item.addon_version,
        ),
        item.full_label,
        None,
    )
    wait_idle(model)


def test_triggered_action_is_recorded_and_stored(model, server):
    trigger(model)

    (item,) = model.get_recent_action_items()
    assert item.action_type == "local"
    assert item.identifier == "maya"
    assert item.label == "Maya"
    assert item.icon == FakeAction.icon.to_data()
    assert item.folder_path == "/f1"
    # Stored on the server as well, not just kept in memory.
    stored = stored_items(server)
    assert [entry["record_id"] for entry in stored] == [item.record_id]


def test_failed_action_is_not_recorded(model, maya):
    maya.failing = True

    trigger(model)

    assert model.get_recent_action_items() == []


def test_context_is_stored_with_names_and_type_icons(model, monkeypatch):
    monkeypatch.setattr(
        ayon_api,
        "get_workfile_info_by_id",
        lambda *args, **kwargs: {"path": "{root[work]}/scene_v001.ma"},
    )

    trigger(model, task_id="t1", workfile_id="wf1")

    (item,) = model.get_recent_action_items()
    assert item.project_code == "PRJ"
    assert item.folder_path == "/f1"
    assert item.folder_icon == "category"
    assert item.task_name == "name_t1"
    assert item.task_icon == "language"
    assert item.task_color == "#ff0000"
    assert item.workfile_name == "scene_v001.ma"


def test_webaction_is_recorded_with_its_listed_icon(model, webactions):
    trigger_webaction(model)

    (item,) = model.get_recent_action_items()
    assert item.action_type == "webaction"
    assert item.identifier == "publish"
    assert item.addon_name == "review"
    assert item.label == "Publish"
    assert item.icon == MaterialSymbolsIcon("publish").to_data()


def test_webaction_that_only_opened_a_form_is_not_recorded(
    model, webactions
):
    webactions.response_type = "form"

    trigger_webaction(model)

    assert webactions.executed
    assert model.get_recent_action_items() == []


def test_history_is_loaded_from_where_it_is_stored(model, server, maya):
    trigger(model, folder_id="a")
    trigger(model, folder_id="b")

    other_session = create_model(FakeController(), maya)
    assert not other_session.are_recent_action_items_loaded()
    other_session.refresh_recent_action_items()

    assert other_session.are_recent_action_items_loaded()
    folders = [i.folder_id for i in other_session.get_recent_action_items()]
    assert folders == ["b", "a"]


def test_local_action_is_shown_as_it_is_now(model, server, maya):
    trigger(model)
    stored_items(server)[0]["label"] = "Maya 2024"
    stored_items(server)[0]["icon"] = {"type": "path", "path": "/other.png"}

    model.refresh_recent_action_items()

    (item,) = model.get_recent_action_items()
    assert item.label == "Maya"
    assert item.icon == FakeAction.icon.to_data()


def test_unknown_stored_keys_do_not_break_loading(model, server):
    trigger(model)
    stored_items(server)[0]["added_by_newer_version"] = True
    stored_items(server).append("not an entry")

    model.refresh_recent_action_items()

    assert len(model.get_recent_action_items()) == 1


def test_action_triggered_before_the_history_was_loaded_keeps_it(
    model, server, maya
):
    trigger(model, folder_id="a")
    trigger(model, folder_id="b")

    # A new session that records an action before anything asked for the
    # history must add to what is stored, not replace it.
    other_session = create_model(FakeController(), maya)
    trigger(other_session, folder_id="c")

    assert [entry["folder_id"] for entry in stored_items(server)] == [
        "c", "b", "a"
    ]


def test_action_is_not_recorded_if_the_history_cannot_be_loaded(
    model, server, maya
):
    trigger(model, folder_id="a")
    stored = copy.deepcopy(stored_items(server))

    server["status_code"] = 500
    other_session = create_model(FakeController(), maya)
    trigger(other_session, folder_id="b")

    assert stored_items(server) == stored
    assert not other_session.are_recent_action_items_loaded()


def test_refresh_does_not_undo_a_change_made_while_it_was_loading(
    model, server, monkeypatch
):
    trigger(model)
    (item,) = model.get_recent_action_items()
    raw_get = ayon_api.raw_get

    def slow_raw_get(endpoint, **kwargs):
        # What the server returns here does not have the change yet
        response = raw_get(endpoint, **kwargs)
        model.set_recent_action_favorite(item.record_id, True)
        return response

    monkeypatch.setattr(ayon_api, "raw_get", slow_raw_get)
    model.refresh_recent_action_items()
    wait_idle(model)

    (item,) = model.get_recent_action_items()
    assert item.favorite


def test_server_support_is_known_after_it_was_checked(model, server):
    assert model.is_recent_actions_supported() is None

    assert model.check_recent_actions_support() is True

    assert model.is_recent_actions_supported() is True


def test_nothing_is_recorded_without_preferences_api(model, server, maya):
    server["status_code"] = 404
    trigger(model, folder_id="a")
    trigger(model, folder_id="b")
    model.refresh_recent_action_items()

    # The actions themselves did run
    assert len(maya.processed) == 2
    assert model.is_recent_actions_supported() is False
    assert not model.are_recent_action_items_loaded()
    assert model.get_recent_action_items() == []
    assert server["preferences"] == {}
    # Only the first request found out the server has no API
    assert server["requests"] == 1


def test_same_action_in_same_context_is_listed_once(model):
    trigger(model)
    (first,) = model.get_recent_action_items()
    model.set_recent_action_favorite(first.record_id, True)
    wait_idle(model)

    trigger(model)

    (item,) = model.get_recent_action_items()
    assert item.record_id != first.record_id
    # Running a favorite again must not quietly unpin it.
    assert item.favorite


def test_favorites_are_not_pushed_out_by_newer_actions(model, server):
    trigger(model, folder_id="pinned")
    (pinned,) = model.get_recent_action_items()
    model.set_recent_action_favorite(pinned.record_id, True)
    wait_idle(model)

    for index in range(RECENT_ACTIONS_MAX + 3):
        trigger(model, folder_id=f"folder_{index}")

    items = model.get_recent_action_items()
    assert len(items) == RECENT_ACTIONS_MAX + 1
    # Favorites come first, the rest from newest to oldest.
    assert items[0].record_id == pinned.record_id
    assert items[1].folder_id == f"folder_{RECENT_ACTIONS_MAX + 2}"
    favorites = [
        entry["record_id"]
        for entry in stored_items(server)
        if entry["favorite"]
    ]
    assert favorites == [pinned.record_id]


def test_removed_entry_stays_removed_after_reload(model):
    trigger(model, folder_id="a")
    trigger(model, folder_id="b")
    item = model.get_recent_action_items()[0]

    model.remove_recent_action(item.record_id)
    wait_idle(model)
    model.refresh_recent_action_items()

    folders = [i.folder_id for i in model.get_recent_action_items()]
    assert item.folder_id not in folders
    assert len(folders) == 1


def test_recent_action_runs_in_its_stored_context(model, maya):
    trigger(model, folder_id="a")
    trigger(model, folder_id="b")
    item_a = model.get_recent_action_items()[1]

    model.trigger_recent_action(item_a.record_id)
    wait_idle(model)

    assert maya.processed[-1].folder_id == "a"
    # Running it again moves it to the top
    folders = [i.folder_id for i in model.get_recent_action_items()]
    assert folders == ["a", "b"]


def test_recent_webaction_runs_with_the_enabled_addon_version(
    model, server, webactions, maya
):
    trigger_webaction(model)
    # A newer bundle enables a newer version of the addon
    webactions.addon_version = "1.1.0"
    other_session = create_model(FakeController(), maya)
    other_session.refresh_recent_action_items()
    (item,) = other_session.get_recent_action_items()

    other_session.trigger_recent_action(item.record_id)
    wait_idle(other_session)

    assert "addonVersion=1.1.0" in webactions.executed[-1]
    assert "identifier=publish" in webactions.executed[-1]


def test_unavailable_recent_action_is_removed_and_reported(
    model, controller, server, maya
):
    trigger(model)
    (item,) = model.get_recent_action_items()
    maya.compatible = False

    model.trigger_recent_action(item.record_id)
    wait_idle(model)

    assert len(maya.processed) == 1
    assert model.get_recent_action_items() == []
    assert stored_items(server) == []
    assert controller.events[-1] == (
        "recent_action.unavailable",
        {"record_id": item.record_id, "full_label": "Maya"},
    )


def test_worker_is_forgotten_when_it_runs_out_of_work(model):
    # The thread only finishes exiting after its last look at the queue. If
    # it is still remembered until then, work queued in between finds it
    # alive, starts no new worker and stays queued.
    history = model._recent_actions
    history._worker = object()

    history._worker_loop()

    assert history._worker is None


def test_work_is_picked_up_again_after_the_worker_went_idle(model):
    trigger(model, folder_id="a")
    assert model._recent_actions._worker is None

    trigger(model, folder_id="b")

    assert len(model.get_recent_action_items()) == 2
