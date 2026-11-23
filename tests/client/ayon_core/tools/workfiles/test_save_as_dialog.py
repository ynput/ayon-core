"""Tests of Save As dialog in workfiles tool."""
from __future__ import annotations

from types import SimpleNamespace

from ayon_core.tools.workfiles.widgets.save_as_dialog import SaveAsDialog


def _save_as_data(folder_id, task_id, **overrides):
    data = {
        "workdir": f"/work/{task_id}",
        "rootless_workdir": f"{{root[work]}}/{task_id}",
        "comment": "last",
        "comment_hints": ["last"],
        "template_has_version": True,
        "template_has_comment": True,
        "ext": ".ma",
        "extensions": [".ma", ".mb"],
        "template_key": "default",
        "last_version": 4,
        "folder_path": f"/folder/{folder_id}",
        "task_name": task_id,
    }
    data.update(overrides)
    return data


def _no_context_save_as_data():
    """Save As data of a context whose entities are empty."""
    return {
        "workdir": None,
        "rootless_workdir": None,
        "comment": None,
        "comment_hints": None,
        "template_has_version": None,
        "template_has_comment": None,
        "ext": None,
        "extensions": None,
        "template_key": None,
        "last_version": None,
        "folder_path": None,
        "task_name": None,
    }


class _FakeController:
    def __init__(
        self,
        current_folder_id="folder-1",
        current_task_name="task-1",
        folder_path=None,
        task_name=None,
        save_as_data=None,
    ) -> None:
        self.save_as_data_contexts = []
        self._current_folder_id = current_folder_id
        self._current_task_name = current_task_name
        self._folder_path = folder_path
        self._task_name = task_name
        self._save_as_data = save_as_data

    def get_selected_context(self):
        return {"folder_id": "folder-1", "task_id": "task-1"}

    def get_current_folder_id(self):
        return self._current_folder_id

    def get_current_task_name(self):
        return self._current_task_name

    def get_workarea_save_as_data(self, folder_id, task_id):
        self.save_as_data_contexts.append((folder_id, task_id))
        if self._save_as_data is not None:
            return self._save_as_data
        return _save_as_data(
            folder_id,
            task_id,
            folder_path=self._folder_path or f"/folder/{folder_id}",
            task_name=self._task_name or task_id,
        )

    def fill_workarea_filepath(
        self, folder_id, task_id, extension, use_last_version, version, comment
    ):
        if use_last_version:
            version = 4
        return SimpleNamespace(
            filename=f"{task_id}_v{version:03}_{comment}{extension}",
            exists=False,
        )


def _accept(qtbot, controller, **kwargs):
    dialog = SaveAsDialog(controller, None, **kwargs)
    qtbot.addWidget(dialog)
    dialog.update_context()
    dialog._on_ok_pressed()
    return dialog.get_result()


def _make_dialog(qtbot, controller, **kwargs):
    dialog = SaveAsDialog(controller, None, **kwargs)
    qtbot.addWidget(dialog)
    dialog.update_context()
    return dialog


def test_save_as_dialog_defaults(qtbot):
    controller = _FakeController()
    result = _accept(qtbot, controller)

    # Selected context, next available version and last comment
    assert controller.save_as_data_contexts == [("folder-1", "task-1")]
    assert result["folder_id"] == "folder-1"
    assert result["task_id"] == "task-1"
    assert result["workdir"] == "/work/task-1"
    assert result["version"] == 4
    assert result["comment"] == "last"
    assert result["filename"] == "task-1_v004_last.ma"
    assert result["description"] == ""


def test_save_as_dialog_inputs(qtbot):
    controller = _FakeController()
    result = _accept(
        qtbot,
        controller,
        folder_id="folder-2",
        task_id="task-2",
        version=7,
        comment="fix",
        description="Note",
        copied_from="/work/file_v001.ma",
    )

    # Context of the inputs is used instead of the selected context
    assert controller.save_as_data_contexts == [("folder-2", "task-2")]
    assert result["folder_id"] == "folder-2"
    assert result["task_id"] == "task-2"
    assert result["workdir"] == "/work/task-2"
    assert result["rootless_workdir"] == "{root[work]}/task-2"
    assert result["version"] == 7
    assert result["comment"] == "fix"
    assert result["filename"] == "task-2_v007_fix.ma"
    # Description has priority over the note of 'copied_from'
    assert result["description"] == "Note"


def test_save_as_dialog_copied_from_note(qtbot):
    result = _accept(qtbot, _FakeController(), copied_from="/work/a_v001.ma")
    assert result["description"] == "Copied from: /work/a_v001.ma"


def _hint_hidden(dialog):
    return (
        dialog._context_hint_label.isHidden()
        and dialog._context_hint_info.isHidden()
    )


def _hint_visible(dialog):
    return (
        not dialog._context_hint_label.isHidden()
        and not dialog._context_hint_info.isHidden()
    )


def test_save_as_dialog_hint_hidden_in_current_context(qtbot):
    dialog = _make_dialog(qtbot, _FakeController())
    assert _hint_hidden(dialog)


def test_save_as_dialog_hint_for_other_context(qtbot):
    dialog = _make_dialog(
        qtbot,
        _FakeController(),
        folder_id="folder-2",
        task_id="task-2",
    )
    assert _hint_visible(dialog)
    assert (
        dialog._context_hint_label.text()
        == "Your context will switch to another folder and task"
    )
    tooltip = "Will switch to: /folder/folder-2 > task-2"
    assert dialog._context_hint_label.toolTip() == tooltip
    assert dialog._context_hint_info.toolTip() == tooltip


def test_save_as_dialog_hint_when_only_task_differs(qtbot):
    dialog = _make_dialog(qtbot, _FakeController(), task_id="task-2")
    assert _hint_visible(dialog)
    assert (
        dialog._context_hint_label.text()
        == "Your context will switch to another task"
    )


def test_save_as_dialog_hint_when_only_folder_differs(qtbot):
    dialog = _make_dialog(qtbot, _FakeController(), folder_id="folder-2")
    assert _hint_visible(dialog)
    assert (
        dialog._context_hint_label.text()
        == "Your context will switch to another folder"
    )


def test_save_as_dialog_hint_without_current_context(qtbot):
    controller = _FakeController(
        current_folder_id=None, current_task_name=None
    )
    dialog = _make_dialog(qtbot, controller)
    assert _hint_visible(dialog)
    assert (
        dialog._context_hint_label.text()
        == "Your context will switch to another folder and task"
    )


def test_save_as_dialog_hint_hidden_without_context_data(qtbot):
    dialog = _make_dialog(qtbot, _FakeController())
    dialog._context_hint_label.setVisible(True)
    dialog._context_hint_info.setVisible(True)
    dialog._update_context_hint({"folder_path": None, "task_name": None})
    assert _hint_hidden(dialog)


def test_save_as_dialog_hint_does_not_widen_dialog(qtbot):
    long_path = "/" + "/".join(["long-folder-name"] * 12)
    short_dialog = _make_dialog(
        qtbot, _FakeController(folder_path="/a", task_name="task-2")
    )
    long_dialog = _make_dialog(
        qtbot, _FakeController(folder_path=long_path, task_name="task-2")
    )
    assert long_dialog.sizeHint().width() == short_dialog.sizeHint().width()
    # The visible message does not depend on the folder path length
    assert (
        long_dialog._context_hint_label.text()
        == short_dialog._context_hint_label.text()
    )


def test_save_as_dialog_hint_hidden_with_empty_entities(qtbot):
    controller = _FakeController(save_as_data=_no_context_save_as_data())
    dialog = _make_dialog(qtbot, controller)
    assert _hint_hidden(dialog)
    assert not dialog._btn_ok.isEnabled()
    assert dialog._preview_widget.text() == "Context is not available."


def test_save_as_dialog_hint_hidden_with_empty_labels(qtbot):
    data = _save_as_data("folder-2", "task-2", folder_path="", task_name="")
    dialog = _make_dialog(qtbot, _FakeController(save_as_data=data))
    assert _hint_hidden(dialog)


def test_save_as_dialog_hint_hidden_with_partial_labels(qtbot):
    data = _save_as_data(
        "folder-2", "task-2", folder_path="/folder/folder-2", task_name=""
    )
    dialog = _make_dialog(qtbot, _FakeController(save_as_data=data))
    assert _hint_hidden(dialog)
