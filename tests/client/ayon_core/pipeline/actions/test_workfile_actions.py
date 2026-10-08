"""Tests of workfile actions api."""
from __future__ import annotations

import sys
from unittest import mock

import pytest

from ayon_core.addon import IPluginPaths
from ayon_core.host import IWorkfileHost
from ayon_core.pipeline.actions import (
    ActionForm,
    WorkfileAreaType,
    WorkfileActionItem,
    WorkfileActionOpenWorkfile,
    WorkfileActionPlugin,
    WorkfileActionRedirect,
    WorkfileActionResult,
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
        self.request_refresh()
        self.request_close()
        self.redirect(
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
        if result is not None:
            return result
        return WorkfileActionResult(message="done")


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


def _create_context(tmp_path, project_settings=None, host=None):
    plugins_dir = tmp_path / "workfile_actions"
    plugins_dir.mkdir(exist_ok=True)
    (plugins_dir / "test_actions.py").write_text(PLUGIN_FILE_CONTENT)
    return WorkfileActionsContext(
        project_name="test_project",
        project_settings=project_settings or {},
        addons_manager=_FakeAddonsManager([_FakeAddon([str(plugins_dir)])]),
        host=host,
    )


def _create_selection(**kwargs):
    kwargs.setdefault("folder_id", "folder-1")
    kwargs.setdefault("task_id", "task-1")
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
        "core.duplicate-workfile",
        "core.explore-here",
    ]
    assert [item.label for item in items[1:3]] == ["A", "Redirect"]


def test_settings_can_disable_plugins(tmp_path):
    context = _create_context(tmp_path, project_settings={
        "core": {
            "workfile_actions": {"ExploreHereAction": {"enabled": False}}
        },
        "test_addon": {
            "workfile_actions": {"RedirectAction": {"order": 100}}
        },
    })
    items = context.get_action_items(
        _create_selection(filepath="/work/file_v001.ma")
    )
    assert [(item.identifier, item.order) for item in items] == [
        ("test.save-changes", -10),
        ("core.duplicate-workfile", 30),
        ("test.redirect", 100),
        ("test.redirect", 100),
    ]


def test_execute_adds_requests_to_result(tmp_path):
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
    # Requests are ignored out of the execution
    context.request_refresh()


def test_ask_to_save_changes(tmp_path):
    host = mock.MagicMock(spec=IWorkfileHost)
    host.name = "testhost"
    host.get_current_workfile.return_value = "/work/current.ma"
    context = _create_context(tmp_path, host=host)
    selection = _create_selection(filepath="/work/file_v001.ma")

    host.workfile_has_unsaved_changes.return_value = False
    result = context.execute_action("test.save-changes", selection, None, {})
    assert result.message == "done"
    assert result.form is None

    host.workfile_has_unsaved_changes.return_value = True
    result = context.execute_action("test.save-changes", selection, None, {})
    assert isinstance(result.form, ActionForm)
    assert result.message is None
    host.save_workfile.assert_not_called()

    result = context.execute_action(
        "test.save-changes",
        selection,
        None,
        {workfile_actions.SAVE_CHANGES_FORM_KEY: False},
    )
    assert result.message == "done"
    host.save_workfile.assert_not_called()

    result = context.execute_action(
        "test.save-changes",
        selection,
        None,
        {workfile_actions.SAVE_CHANGES_FORM_KEY: True},
    )
    assert result.message == "done"
    host.save_workfile.assert_called_once_with("/work/current.ma")


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
    with mock.patch.object(
        sys.modules[plugin.__module__],
        "copy_workfile_to_context",
        return_value=dst_path,
    ) as copy_mock:
        result = context.execute_action(identifier, _selection(), None, {})

    assert result.success is True
    # Workfile is only duplicated, the scene is not saved and the action
    #   does not ask for unsaved changes
    args, kwargs = copy_mock.call_args
    assert args == (str(workfile_path), folder_entity, task_entity)
    assert kwargs["comment"] == "blocking"
    assert kwargs["open_workfile"] is False
    assert result.form is None
    host.save_workfile.assert_not_called()
    host.workfile_has_unsaved_changes.assert_not_called()
    # The tool is asked to open the duplicated workfile
    assert result.close_tool is False
    assert result.open_workfile == WorkfileActionOpenWorkfile(
        filepath=dst_path, folder_id="folder-1", task_id="task-1"
    )
    # New workfile is selected if a user cancels the opening
    assert result.redirect == WorkfileActionRedirect(
        folder_id="folder-1",
        task_name="comp",
        workfile_name="file_v002.ma",
    )


def test_duplicate_workfile(tmp_path):
    context = _create_context(tmp_path)
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
    assert all(
        other_item.quick_action
        for other_item in context.get_action_items(selection)
        if other_item.identifier != identifier
    )
    # Is available only for selected workarea workfile
    assert _get_item(_create_selection()) is None
    assert _get_item(_create_selection(
        area="published",
        representation_id="repre-1",
        filepath="/publish/file_v001.ma",
    )) is None

    # The tool is asked to duplicate the workfile
    result = context.execute_action(identifier, selection, None, {})
    assert result.duplicate_workfile == "/work/file_v001.ma"


def test_result_json_conversion():
    result = WorkfileActionResult(
        message="Message",
        success=False,
        refresh=True,
        open_workfile=WorkfileActionOpenWorkfile(
            filepath="/work/file_v002.ma", task_id="task-1"
        ),
        duplicate_workfile="/work/file_v001.ma",
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
