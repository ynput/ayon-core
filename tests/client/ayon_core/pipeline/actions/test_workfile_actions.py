"""Tests of workfile actions api."""
from __future__ import annotations

import sys
from unittest import mock

import pytest

from ayon_core.addon import IPluginPaths
from ayon_core.host import IWorkfileHost
from ayon_core.pipeline.actions import (
    WorkfileAreaType,
    WorkfileActionItem,
    WorkfileActionPlugin,
    WorkfileActionRedirect,
    WorkfileActionResult,
    WorkfileActionSaveAsFormInputs,
    WorkfileActionSaveAsValues,
    WorkfileActionSelection,
    WorkfileActionsContext,
)
from ayon_core.pipeline.actions import workfile as workfile_actions

PLUGIN_FILE_CONTENT = '''
from ayon_core.pipeline.actions import (
    WorkfileActionItem,
    WorkfileActionPlugin,
    WorkfileActionResult,
    WorkfileSimpleActionPlugin,
)


class RedirectAction(WorkfileActionPlugin):
    identifier = "test.redirect"
    settings_category = "test_addon"
    order = 5

    def get_action_items(self, selection):
        return [
            WorkfileActionItem(label="Redirect", order=self.order),
            WorkfileActionItem(
                label="A", group_label="Group", order=self.order
            ),
        ]

    def execute_action(self, selection, data, form_values):
        return WorkfileActionResult(
            refresh=True, close_tool=True
        ).set_redirect(
            task_entity={"folderId": "folder-2", "name": "comp"},
            workfile_name="file_v002.ma",
        )


class SaveChangesAction(WorkfileSimpleActionPlugin):
    identifier = "test.save-changes"
    label = "Save changes"
    order = -10

    def is_compatible(self, selection):
        return selection.has_workfile()

    def execute_simple_action(self, selection, form_values):
        result = self.ask_to_save_changes(form_values)
        if isinstance(result, WorkfileActionResult):
            return result
        return WorkfileActionResult(message=f"saved: {result}")


class CrashingAction(WorkfileActionPlugin):
    identifier = "test.crashing"

    def get_action_items(self, selection):
        raise ValueError("Test crash")

    def execute_action(self, selection, data, form_values):
        pass
'''


class _FakeAddon(IPluginPaths):
    def __init__(self, paths):
        self._paths = paths

    def get_workfile_action_plugin_paths(self, host_name):
        return list(self._paths)


class _FakeAddonsManager:
    def __init__(self, addons):
        self.addons = addons


def _create_host():
    host = mock.MagicMock(spec=IWorkfileHost)
    host.name = "testhost"
    host.get_current_project_name.return_value = "test_project"
    return host


def _create_context(tmp_path, project_settings=None, host=None):
    plugins_dir = tmp_path / "workfile_actions"
    plugins_dir.mkdir(exist_ok=True)
    (plugins_dir / "test_actions.py").write_text(PLUGIN_FILE_CONTENT)
    if host is None:
        host = _create_host()
    return WorkfileActionsContext(
        host,
        project_settings=project_settings or {},
        addons_manager=_FakeAddonsManager([_FakeAddon([str(plugins_dir)])]),
    )


def _create_selection(**kwargs):
    kwargs.setdefault("folder_id", "folder-1")
    kwargs.setdefault("task_id", "task-1")
    kwargs.setdefault("project_settings", {})
    area = kwargs.pop("area", WorkfileAreaType.workarea)
    return WorkfileActionSelection("test_project", area, **kwargs)


@pytest.fixture(autouse=True)
def _no_server_calls():
    """Make sure the tests do not try to reach AYON server."""
    with mock.patch.object(
        workfile_actions, "ayon_api", mock.Mock(spec=[])
    ):
        yield


def test_discovery_and_sorting(tmp_path):
    context = _create_context(tmp_path)
    selection = _create_selection(filepath="/work/file_v001.ma")

    items = context.get_action_items(selection)
    identifiers = [item.identifier for item in items]
    # Sorted by order, plugins from core and from addon are available and
    #   crashing plugin does not break the others
    assert identifiers == [
        "test.save-changes",
        "test.redirect",
        "test.redirect",
        "core.increment-and-open",
        "core.duplicate-workfile",
        "core.copy-file",
        "core.copy-file",
        "core.explore-here",
    ]
    assert [item.label for item in items[1:3]] == ["A", "Redirect"]


def test_settings_can_disable_plugins(tmp_path):
    context = _create_context(tmp_path)
    items = context.get_action_items(_create_selection(
        filepath="/work/file_v001.ma",
        project_settings={
            "core": {
                "workfile_actions": {
                    "ExploreHereAction": {"enabled": False}
                }
            },
        },
    ))
    # Settings of the selection project are used
    assert [item.identifier for item in items] == [
        "test.save-changes",
        "test.redirect",
        "test.redirect",
        "core.increment-and-open",
        "core.duplicate-workfile",
        "core.copy-file",
        "core.copy-file",
    ]


def test_execute_returns_result(tmp_path):
    context = _create_context(tmp_path)
    result = context.execute_action(
        "test.redirect", _create_selection(), None, {}
    )
    assert result == WorkfileActionResult(
        refresh=True,
        close_tool=True,
        redirect=WorkfileActionRedirect(
            folder_id="folder-2",
            task_name="comp",
            workfile_name="file_v002.ma",
        ),
    )
    # Plugin that does not return a result
    result = context.execute_action(
        "test.crashing", _create_selection(), None, {}
    )
    assert result == WorkfileActionResult()


def test_result_helpers():
    task_entity = {"id": "task-1", "folderId": "folder-1", "name": "comp"}
    result = WorkfileActionResult("Copied").set_redirect(
        task_entity=task_entity, workfile_name="file_v002.ma"
    )
    assert result.message == "Copied"
    assert result.redirect == WorkfileActionRedirect(
        folder_id="folder-1",
        task_name="comp",
        workfile_name="file_v002.ma",
    )

    # Folder entity, published area and context of the selection
    result = WorkfileActionResult().set_redirect(
        folder_entity={"id": "folder-2"},
        representation_id="repre-1",
        area="published",
    )
    assert result.redirect == WorkfileActionRedirect(
        folder_id="folder-2",
        representation_id="repre-1",
        area=WorkfileAreaType.published,
    )


def test_ask_to_save_changes(tmp_path):
    host = mock.MagicMock(spec=IWorkfileHost)
    host.name = "testhost"
    host.get_current_workfile.return_value = "/work/current.ma"
    context = _create_context(tmp_path, host=host)
    selection = _create_selection(filepath="/work/file_v001.ma")

    # No unsaved changes, nothing is saved
    host.workfile_has_unsaved_changes.return_value = False
    result = context.execute_action("test.save-changes", selection, None, {})
    assert result.message == "saved: False"
    assert result.show_save_changes_form is False

    host.workfile_has_unsaved_changes.return_value = True
    result = context.execute_action("test.save-changes", selection, None, {})
    assert result.show_save_changes_form is True
    assert result.form is None
    assert result.message is None
    host.save_workfile.assert_not_called()

    result = context.execute_action(
        "test.save-changes",
        selection,
        None,
        {workfile_actions.SAVE_CHANGES_FORM_KEY: False},
    )
    assert result.message == "saved: False"
    host.save_workfile.assert_not_called()

    result = context.execute_action(
        "test.save-changes",
        selection,
        None,
        {workfile_actions.SAVE_CHANGES_FORM_KEY: True},
    )
    assert result.message == "saved: True"
    host.save_workfile.assert_called_once_with("/work/current.ma")

    # Failed save stops the action with a failure message
    host.save_workfile.side_effect = RuntimeError("Save failed")
    result = context.execute_action(
        "test.save-changes",
        selection,
        None,
        {workfile_actions.SAVE_CHANGES_FORM_KEY: True},
    )
    assert result.success is False
    assert result.message == "Failed to save current workfile"


def test_selection_areas():
    selection = _create_selection(filepath="/work/file_v001.ma")
    assert selection.is_workarea()
    assert not selection.is_published()
    assert selection.has_workfile()
    assert selection.filename == "file_v001.ma"

    assert not _create_selection().has_workfile()

    published = _create_selection(
        area="published",
        representation_id="repre-1",
        filepath="/publish/file_v001.ma",
    )
    assert published.is_published()
    assert published.has_workfile()
    assert not _create_selection(area="published").has_workfile()


def test_selection_uses_prepared_entities():
    folder_entity = {"id": "folder-1"}
    task_entity = {"id": "task-1", "folderId": "folder-1", "name": "comp"}
    selection = _create_selection(
        folder_entity=folder_entity,
        task_entity=task_entity,
        workdir="/work",
        project_settings={"core": {}},
    )
    # Server would be called if entities were not used ('ayon_api' is mocked)
    assert selection.get_folder_entity() == folder_entity
    assert selection.get_task_entity() == task_entity
    assert selection.get_workdir() == "/work"
    assert selection.project_settings == {"core": {}}
    # Nothing to look for without ids
    assert selection.get_workfile_entity() is None
    assert selection.get_representation_entity() is None
    assert selection.get_version_entity() is None


def test_explore_here_compatibility(tmp_path):
    context = _create_context(tmp_path)

    def _explore_available(selection):
        return any(
            item.identifier == "core.explore-here"
            for item in context.get_action_items(selection)
        )

    # Work directory is opened if workfile is not selected
    assert _explore_available(_create_selection())
    assert not _explore_available(_create_selection(task_id=None))
    # There is no directory to open in published area without a workfile
    assert not _explore_available(_create_selection(area="published"))
    assert _explore_available(_create_selection(
        area="published",
        representation_id="repre-1",
        filepath="/publish/file_v001.ma",
    ))


def test_set_context(tmp_path):
    identifier = "core.set-context"
    host = _create_host()
    host.get_current_context.return_value = {
        "project_name": "test_project",
        "folder_path": "/shots/sh010",
        "task_name": "comp",
    }
    folder_entity = {"id": "folder-1", "path": "/shots/sh020"}
    task_entity = {
        "id": "task-1", "folderId": "folder-1", "name": "comp",
        "label": "Compositing",
    }

    def _selection(**kwargs):
        kwargs.setdefault("folder_entity", folder_entity)
        kwargs.setdefault("task_entity", task_entity)
        kwargs.setdefault("project_settings", {
            "core": {
                "workfile_actions": {"SetContextAction": {"enabled": True}}
            },
        })
        return _create_selection(
            project_entity={"name": "test_project"},
            project_anatomy=mock.Mock(),
            **kwargs
        )

    context = _create_context(tmp_path, host=host)

    def _is_available(selection):
        return any(
            item.identifier == identifier
            for item in context.get_action_items(selection)
        )

    # Disabled by default
    assert not _is_available(_selection(project_settings={}))

    # Available for a task with or without selected workfile, in both areas
    assert _is_available(_selection())
    assert _is_available(_selection(filepath="/work/file_v001.ma"))
    assert _is_available(_selection(area="published"))
    assert not _is_available(_selection(task_id=None))
    # Hidden if the task is the current context
    assert not _is_available(_selection(
        folder_entity={"id": "folder-1", "path": "/shots/sh010"}
    ))

    result = context.execute_action(identifier, _selection(), None, {})
    args, kwargs = host.set_current_context.call_args
    assert args == (folder_entity, task_entity)
    assert kwargs["project_entity"] == {"name": "test_project"}
    assert result.success is True
    assert result.refresh is True
    assert "Compositing" in result.message


def test_increment_and_open(tmp_path):
    host = mock.MagicMock(spec=IWorkfileHost)
    host.name = "testhost"
    host.workfile_has_unsaved_changes.return_value = False
    context = _create_context(tmp_path, host=host)
    identifier = "core.increment-and-open"

    workfile_path = tmp_path / "file_v001.ma"
    workfile_path.write_text("")
    folder_entity = {"id": "folder-1"}
    task_entity = {"id": "task-1", "folderId": "folder-1", "name": "comp"}
    workfile_info = mock.Mock(available=True, comment="blocking")

    def _selection(**kwargs):
        kwargs.setdefault("filepath", str(workfile_path))
        return _create_selection(
            folder_entity=folder_entity,
            task_entity=task_entity,
            project_entity={"name": "test_project"},
            project_anatomy=mock.Mock(),
            project_settings={},
            workfile_info=workfile_info,
            **kwargs
        )

    def _is_available(selection):
        return any(
            item.identifier == identifier
            for item in context.get_action_items(selection)
        )

    # Is available only for selected workarea workfile
    assert _is_available(_selection())
    assert not _is_available(_selection(filepath=None))
    assert not _is_available(
        _selection(area="published", representation_id="repre-1")
    )

    result = context.execute_action(
        identifier, _selection(filepath="/missing/file_v001.ma"), None, {}
    )
    assert result.success is False
    assert not result.close_tool

    dst_path = str(tmp_path / "file_v002.ma")
    plugin = context._get_plugins()[identifier]
    plugin_module = sys.modules[plugin.__module__]

    # Unsaved changes: a user is asked first and nothing is copied yet,
    #   cancel of the form does not trigger the action again
    host.workfile_has_unsaved_changes.return_value = True
    with mock.patch.object(
        plugin_module, "copy_workfile_to_context", return_value=dst_path
    ) as copy_mock:
        result = context.execute_action(identifier, _selection(), None, {})
    assert result.show_save_changes_form is True
    assert result.form is None
    assert not result.close_tool
    copy_mock.assert_not_called()
    host.save_workfile.assert_not_called()

    # User decided to not save the changes
    with mock.patch.object(
        plugin_module, "copy_workfile_to_context", return_value=dst_path
    ) as copy_mock:
        result = context.execute_action(
            identifier,
            _selection(),
            None,
            {workfile_actions.SAVE_CHANGES_FORM_KEY: False},
        )
    host.save_workfile.assert_not_called()
    copy_mock.assert_called_once()
    assert result.close_tool is True

    # No unsaved changes: copied and opened right away
    host.workfile_has_unsaved_changes.return_value = False
    with mock.patch.object(
        plugin_module, "copy_workfile_to_context", return_value=dst_path
    ) as copy_mock:
        result = context.execute_action(identifier, _selection(), None, {})

    assert result.success is True
    assert result.form is None
    args, kwargs = copy_mock.call_args
    assert args == (str(workfile_path), folder_entity, task_entity)
    assert kwargs["comment"] == "blocking"
    # The copy is opened by the host and the tool is closed
    assert kwargs["open_workfile"] is True
    assert result.close_tool is True
    host.save_workfile.assert_not_called()


def test_project_name_comes_from_host(tmp_path):
    host = _create_host()
    host.get_current_project_name.return_value = "host_project"
    context = _create_context(tmp_path, host=host)
    assert context.get_project_name() == "host_project"

    # Settings of the host project are used if are not prepared
    context.reset()
    with mock.patch.object(
        workfile_actions,
        "get_project_settings",
        return_value={"core": {}},
    ) as get_settings_mock:
        assert context.get_project_settings() == {"core": {}}
    get_settings_mock.assert_called_once_with("host_project")


def test_copy_file_items(tmp_path):
    context = _create_context(tmp_path)
    identifier = "core.copy-file"

    def _get_items(selection):
        return [
            item
            for item in context.get_action_items(selection)
            if item.identifier == identifier
        ]

    items = _get_items(_create_selection(filepath="/work/file_v001.ma"))
    assert [(item.label, item.data, item.quick_action) for item in items] == [
        ("Copy file path", {"action": "copy-path"}, False),
        ("Copy file", {"action": "copy-file"}, False),
    ]
    # Published workfile can be copied too
    assert len(_get_items(_create_selection(
        area="published",
        representation_id="repre-1",
        filepath="/publish/file_v001.ma",
    ))) == 2
    # There is nothing to copy without selected workfile
    assert _get_items(_create_selection()) == []
    assert _get_items(_create_selection(area="published")) == []


def test_duplicate_workfile(tmp_path):
    host = _create_host()
    context = _create_context(tmp_path, host=host)
    identifier = "core.duplicate-workfile"

    def _get_item(selection):
        return next(
            (
                item
                for item in context.get_action_items(selection)
                if item.identifier == identifier
            ),
            None
        )

    selection = _create_selection(filepath="/work/file_v001.ma")
    item = _get_item(selection)
    # Duplicate is available only in context menu by default
    assert item.quick_action is False
    # Is available only for selected workarea workfile
    assert _get_item(_create_selection()) is None
    assert _get_item(_create_selection(
        area="published",
        representation_id="repre-1",
        filepath="/publish/file_v001.ma",
    )) is None

    # The tool is asked to show the Save As dialog first, nothing is copied
    result = context.execute_action(identifier, selection, None, {})
    assert result.show_save_as_form == WorkfileActionSaveAsFormInputs(
        folder_id="folder-1",
        task_id="task-1",
        description="Copied from: /work/file_v001.ma",
    )
    host.copy_workfile.assert_not_called()

    # The action is triggered again with values of the accepted dialog
    folder_entity = {"id": "folder-1"}
    task_entity = {"id": "task-1", "folderId": "folder-1", "name": "comp"}
    project_anatomy = mock.Mock()
    selection = _create_selection(
        filepath="/work/file_v001.ma",
        folder_entity=folder_entity,
        task_entity=task_entity,
        project_entity={"name": "test_project"},
        project_anatomy=project_anatomy,
        project_settings={},
    )
    form_values = {
        workfile_actions.SAVE_AS_FORM_KEY: {
            "folder_id": "folder-1",
            "task_id": "task-1",
            "workdir": str(tmp_path),
            "rootless_workdir": "{root[work]}/comp",
            "filename": "file_v005_note.ma",
            "template_key": "default",
            "version": 5,
            "comment": "note",
            "description": "Copied from: /work/file_v001.ma",
        }
    }
    result = context.execute_action(identifier, selection, None, form_values)

    args, kwargs = host.copy_workfile.call_args
    assert args == (
        "/work/file_v001.ma",
        str(tmp_path / "file_v005_note.ma"),
        folder_entity,
        task_entity,
    )
    assert kwargs["version"] == 5
    assert kwargs["comment"] == "note"
    assert kwargs["description"] == "Copied from: /work/file_v001.ma"
    assert kwargs["open_workfile"] is False
    prepared_data = kwargs["prepared_data"]
    assert prepared_data.rootless_path == "{root[work]}/comp/file_v005_note.ma"
    assert prepared_data.anatomy is project_anatomy
    # The new workfile is selected in the tool
    assert result.success is True
    assert result.redirect == WorkfileActionRedirect(
        folder_id="folder-1",
        task_name="comp",
        workfile_name="file_v005_note.ma",
    )

    # Failed copy is reported
    host.copy_workfile.side_effect = RuntimeError("Copy failed")
    result = context.execute_action(identifier, selection, None, form_values)
    assert result.success is False
    assert result.redirect is None


def test_save_as_values_from_form_values():
    assert WorkfileActionSaveAsValues.from_form_values({}) is None
    values = WorkfileActionSaveAsValues.from_form_values({
        workfile_actions.SAVE_AS_FORM_KEY: {
            "folder_id": "folder-1",
            "task_id": "task-1",
            "workdir": "/work/comp",
            "rootless_workdir": "{root[work]}/comp",
            "filename": "file_v002.ma",
            "version": 2,
            # Additional values of the dialog are ignored
            "template_key": "default",
        }
    })
    assert values.comment is None
    assert values.filepath.replace("\\", "/") == "/work/comp/file_v002.ma"
    assert values.rootless_path == "{root[work]}/comp/file_v002.ma"


def test_result_json_conversion():
    result = WorkfileActionResult(
        message="Message",
        success=False,
        refresh=True,
        show_save_as_form=WorkfileActionSaveAsFormInputs(
            folder_id="folder-2",
            task_id="task-2",
            version=3,
            comment="note",
            description="Note",
            extension=".ma",
        ),
        show_save_changes_form=True,
        redirect=WorkfileActionRedirect(
            folder_id="folder-1",
            task_name="comp",
            area=WorkfileAreaType.published,
        ),
    )
    data = result.to_json_data()
    assert data["redirect"]["area"] == "published"
    assert WorkfileActionResult.from_json_data(data) == result


def test_plugin_requires_implementation():
    class _Plugin(WorkfileActionPlugin):
        pass

    with pytest.raises(TypeError):
        _Plugin(mock.Mock())

    item = WorkfileActionItem(label="Label")
    assert item.identifier is None
    assert item.order == 0
