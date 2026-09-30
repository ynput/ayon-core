"""Tests for the model persisting the recent actions of the launcher."""

from __future__ import annotations

import copy
import time
from typing import Any, Optional

import pytest

import ayon_api

from ayon_core.tools.launcher.abstract import (
    RECENT_ACTIONS_MAX,
    ContextLabels,
)
from ayon_core.tools.launcher.models.recent_actions import (
    RecentActionsModel,
)


class FakeController:
    """Just what the model asks of the launcher controller."""

    def __init__(self) -> None:
        self.callbacks: dict[str, Any] = {}

    def register_event_callback(self, topic, callback) -> None:
        self.callbacks[topic] = callback

    def emit(self, topic: str, event: dict[str, Any]) -> None:
        self.callbacks[topic](event)

    def get_action_item(self, *args, **kwargs) -> Optional[Any]:
        return None

    def get_local_action_label_icon(self, identifier) -> Optional[Any]:
        return None

    def get_context_labels(
        self, project_name, folder_id, task_id, workfile_id
    ) -> ContextLabels:
        return ContextLabels(folder_path=f"/{folder_id}")


@pytest.fixture
def user_data(monkeypatch) -> dict[str, Any]:
    """In memory stand-in for the data of the current AYON user."""
    user = {"name": "tester", "data": {}}

    class Response:
        def raise_for_status(self) -> None:
            pass

    def raw_patch(endpoint, **kwargs):
        user["data"] = copy.deepcopy(kwargs["json"]["data"])
        return Response()

    monkeypatch.setattr(ayon_api, "get_user", lambda: copy.deepcopy(user))
    monkeypatch.setattr(ayon_api, "raw_patch", raw_patch)
    return user


@pytest.fixture
def controller() -> FakeController:
    return FakeController()


@pytest.fixture
def model(controller, user_data) -> RecentActionsModel:
    return RecentActionsModel(controller)


def wait_idle(model: RecentActionsModel, timeout: float = 5.0) -> None:
    """Wait for the recording worker to have nothing left to do."""
    end = time.time() + timeout
    while time.time() < end:
        worker = model._worker
        if (
            not model._queued_triggers
            and not model._save_requested
            and (worker is None or not worker.is_alive())
        ):
            return
        time.sleep(0.005)
    raise AssertionError("Recent actions worker did not finish.")


def trigger(controller, model, folder_id="f1", identifier="maya", **kwargs):
    event = {
        "identifier": identifier,
        "failed": False,
        "full_label": "Maya",
        "project_name": "project",
        "folder_id": folder_id,
        "task_id": None,
        "workfile_id": None,
        "addon_name": None,
    }
    event.update(kwargs)
    controller.emit("action.trigger.finished", event)
    wait_idle(model)


def test_triggered_action_is_recorded_and_stored(
    controller, model, user_data
):
    trigger(controller, model)

    (item,) = model.get_recent_action_items()
    assert item.identifier == "maya"
    assert item.folder_path == "/f1"
    # Stored on the server as well, not just kept in memory.
    stored = user_data["data"]["recentActions"]
    assert [entry["record_id"] for entry in stored] == [item.record_id]


def test_failed_action_is_not_recorded(controller, model):
    trigger(controller, model, failed=True)

    assert model.get_recent_action_items() == []


def test_same_action_in_same_context_is_listed_once(controller, model):
    trigger(controller, model)
    (first,) = model.get_recent_action_items()
    model.set_favorite(first.record_id, True)
    wait_idle(model)

    trigger(controller, model)

    (item,) = model.get_recent_action_items()
    assert item.record_id != first.record_id
    # Running a favorite again must not quietly unpin it.
    assert item.favorite


def test_favorites_are_not_pushed_out_by_newer_actions(controller, model):
    trigger(controller, model, folder_id="pinned")
    (pinned,) = model.get_recent_action_items()
    model.set_favorite(pinned.record_id, True)
    wait_idle(model)

    for index in range(RECENT_ACTIONS_MAX + 3):
        trigger(controller, model, folder_id=f"folder_{index}")

    items = model.get_recent_action_items()
    assert len(items) == RECENT_ACTIONS_MAX + 1
    # Favorites come first, the rest from newest to oldest.
    assert items[0].record_id == pinned.record_id
    assert items[1].folder_id == f"folder_{RECENT_ACTIONS_MAX + 2}"


def test_removed_entry_stays_removed_after_reload(controller, model):
    trigger(controller, model, folder_id="a")
    trigger(controller, model, folder_id="b")
    item = model.get_recent_action_items()[0]

    model.remove_recent_action(item.record_id)
    wait_idle(model)
    model.refresh()

    folders = [i.folder_id for i in model.get_recent_action_items()]
    assert item.folder_id not in folders
    assert len(folders) == 1


def test_worker_is_forgotten_when_it_runs_out_of_work(model):
    # The thread only finishes exiting after its last look at the queue. If
    # it is still remembered until then, work queued in between finds it
    # alive, starts no new worker and stays queued.
    model._worker = object()

    model._worker_loop()

    assert model._worker is None


def test_work_is_picked_up_again_after_the_worker_went_idle(
    controller, model
):
    trigger(controller, model, folder_id="a")
    assert model._worker is None

    trigger(controller, model, folder_id="b")

    assert len(model.get_recent_action_items()) == 2
