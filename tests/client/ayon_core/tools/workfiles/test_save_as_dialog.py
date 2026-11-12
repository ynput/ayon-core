"""Tests of Save As dialog in workfiles tool."""
from __future__ import annotations

from types import SimpleNamespace

from ayon_core.tools.workfiles.widgets.save_as_dialog import SaveAsDialog


class _FakeController:
    def __init__(self) -> None:
        self.save_as_data_contexts = []

    def get_selected_context(self):
        return {"folder_id": "folder-1", "task_id": "task-1"}

    def get_workarea_save_as_data(self, folder_id, task_id):
        self.save_as_data_contexts.append((folder_id, task_id))
        return {
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
        }

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
