"""Tests for the workfile template builder tool controller."""
import logging

import pytest

from ayon_core.lib import attribute_definitions
from ayon_core.pipeline.workfile import (
    workfile_template_builder as wtb,
)
from ayon_core.pipeline.workfile.workfile_template_builder import (
    AbstractTemplateBuilder,
    PlaceholderItem,
    PlaceholderPlugin,
    PlaceholderPreview,
    TemplatePreset,
)
from ayon_core.tools.workfile_template_build.abstract import (
    BuildContextItem,
    BUILD_CONTEXT_CHANGED_TOPIC,
    PLACEHOLDER_CREATED_TOPIC,
    PLACEHOLDERS_REFRESHED_TOPIC,
    PLACEHOLDER_DELETED_TOPIC,
    PLACEHOLDER_UPDATED_TOPIC,
    PlaceholderCompletionsError,
    PlaceholderOptionsError,
)
from ayon_core.tools.workfile_template_build.build_results import (
    MAX_BUILD_HISTORY,
)
from ayon_core.tools.workfile_template_build.control import (
    WorkfileTemplateBuilderController,
)


@pytest.fixture(autouse=True)
def _fake_context_entities(monkeypatch):
    """Resolve folder/task lookups in controller context validation."""

    def get_folder_by_path(project_name, folder_path):
        if not folder_path:
            return None
        return {
            "id": "folder-1",
            "path": folder_path,
            "name": folder_path.rsplit("/", 1)[-1],
        }

    def get_task_by_name(project_name, folder_id, task_name):
        if not task_name:
            return None
        return {
            "id": "task-1",
            "name": task_name,
            "taskType": "animation",
        }

    monkeypatch.setattr(wtb, "get_folder_by_path", get_folder_by_path)
    monkeypatch.setattr(wtb, "get_task_by_name", get_task_by_name)


class _FakeScene:
    """Scene stand-in shared by the plugin and the tests."""

    def __init__(self):
        self.nodes = {}
        self.selected = []
        self.ran = []
        self.populated = []
        self._counter = 0

    def add(self, data):
        self._counter += 1
        identifier = "node_{}".format(self._counter)
        self.nodes[identifier] = dict(data)
        return identifier


class _Plugin(PlaceholderPlugin):
    label = "Fake"
    identifier = "fake"
    icon = {"type": "material-symbols", "name": "download", "color": "#fff"}

    # Set by tests to make an action fail
    fail_on = None

    def __init__(self, builder):
        super().__init__(builder)
        self.scene = builder.scene

    def get_placeholder_options(self, options=None):
        if self.fail_on == "options":
            raise RuntimeError("options boom")
        options = options or {}
        return [
            attribute_definitions.TextDef(
                "name", label="Name", default=options.get("name")
            ),
        ]

    def get_placeholder_label(self, placeholder_item):
        return placeholder_item.data.get("name") or "<unnamed>"

    def get_placeholder_preview(self, placeholder_data):
        return PlaceholderPreview(title="Preview of {}".format(
            placeholder_data.get("name")
        ))

    def get_placeholder_completions(self, placeholder_data):
        if self.fail_on == "completions":
            raise RuntimeError("completions boom")
        return {"name": ["one", "two"]}

    def create_placeholder(self, placeholder_data):
        if self.fail_on == "create":
            raise RuntimeError("create boom")
        # Returns nothing on purpose, like some host implementations
        if self.fail_on == "create_partial":
            self.scene.add(placeholder_data)
            raise RuntimeError("create partial boom")
        self.scene.add(placeholder_data)

    def update_placeholder(self, placeholder_item, placeholder_data):
        self.scene.nodes[placeholder_item.scene_identifier] = dict(
            placeholder_data
        )
        if self.fail_on == "update_partial":
            raise RuntimeError("update partial boom")

    def collect_placeholders(self):
        if self.fail_on == "collect":
            raise RuntimeError("collect boom")
        return [
            PlaceholderItem(identifier, dict(data), self)
            for identifier, data in self.scene.nodes.items()
        ]

    def populate_placeholder(self, placeholder):
        if self.fail_on == "populate":
            raise RuntimeError("populate boom")
        self.scene.populated.append(placeholder.scene_identifier)

    def delete_placeholder(self, placeholder_item):
        self.scene.nodes.pop(placeholder_item.scene_identifier, None)
        if self.fail_on == "delete_partial":
            raise RuntimeError("delete partial boom")

    def select_placeholder(self, placeholder_item):
        self.scene.selected = [placeholder_item.scene_identifier]

    def repopulate_placeholder(self, placeholder):
        if self.fail_on == "run":
            raise RuntimeError("run boom")
        if self.fail_on == "run_error":
            placeholder.set_failed(RuntimeError("run error"))
            return
        self.scene.ran.append(placeholder.scene_identifier)


class _ReadOnlyPlugin(_Plugin):
    """Plugin without delete and select support."""
    label = "Read only"
    identifier = "fake.readonly"

    delete_placeholder = PlaceholderPlugin.delete_placeholder
    select_placeholder = PlaceholderPlugin.select_placeholder
    repopulate_placeholder = PlaceholderPlugin.repopulate_placeholder

    def collect_placeholders(self):
        return []

    def populate_placeholder(self, placeholder):
        pass


class _EventCollector:
    """Keeps received events.

    Event callbacks are held by weak reference, so the collector has to stay
    alive for the whole test.
    """

    def __init__(self):
        self.events = []

    def collect(self, event):
        self.events.append(event)


class _Builder(AbstractTemplateBuilder):
    def __init__(self, host=None):
        super().__init__(host)
        self.scene = _FakeScene()
        self.refresh_count = 0

    def get_placeholder_plugin_classes(self):
        return [_Plugin, _ReadOnlyPlugin]

    def import_template(self, path):
        return True

    def refresh(self):
        self.refresh_count += 1
        super().refresh()


@pytest.fixture
def controller():
    output = WorkfileTemplateBuilderController(_Builder(None))
    yield output
    output.close()


class TestControllerWithoutBuilder:
    def test_no_builder_is_reported(self):
        controller = WorkfileTemplateBuilderController(None)
        assert not controller.is_builder_available()
        assert controller.get_placeholder_plugin_items() == []
        assert controller.get_placeholder_items() == []
        assert controller.get_placeholder_options("fake") == []
        assert controller.get_placeholder_preview("fake", {}) is None
        assert controller.get_placeholder_completions("fake", {}) == {}

    def test_actions_fail_gracefully(self):
        controller = WorkfileTemplateBuilderController(None)
        result = controller.create_placeholder("fake", {})
        assert not result.success
        assert result.error_title


class TestPluginItems:
    def test_capabilities_are_exposed(self, controller):
        items_by_id = {
            item.identifier: item
            for item in controller.get_placeholder_plugin_items()
        }
        assert items_by_id["fake"].delete_supported
        assert items_by_id["fake"].select_supported
        assert items_by_id["fake"].run_supported
        assert not items_by_id["fake.readonly"].delete_supported
        assert not items_by_id["fake.readonly"].select_supported

    def test_items_are_sorted_by_label(self, controller):
        labels = [
            item.label for item in controller.get_placeholder_plugin_items()
        ]
        assert labels == sorted(labels)

    def test_duplicate_scene_identifiers_are_reported(
        self, controller, monkeypatch
    ):
        plugin = controller._builder.placeholder_plugins["fake"]
        placeholders = [
            PlaceholderItem("same", {"name": "one"}, plugin),
            PlaceholderItem("same", {"name": "two"}, plugin),
        ]
        monkeypatch.setattr(
            controller._builder,
            "get_placeholders",
            lambda **_kwargs: placeholders,
        )

        items = controller.get_placeholder_items()

        assert len(items) == 1
        assert items[0].scene_identifier == "same"
        assert "Duplicate" in controller.get_placeholders_error()


class TestCreatePlaceholder:
    def test_scene_identifier_is_resolved_without_return_value(
        self, controller
    ):
        """Plugins may not return the created item, find it by comparison."""
        result = controller.create_placeholder("fake", {"name": "one"})

        assert result.success
        assert result.scene_identifier == "node_1"

    def test_created_placeholder_is_listed_right_away(self, controller):
        controller.get_placeholder_items()  # fill the cache
        controller.create_placeholder("fake", {"name": "one"})

        labels = [item.label for item in controller.get_placeholder_items()]
        assert labels == ["one"]

    def test_event_is_emitted(self, controller):
        collector = _EventCollector()
        controller.register_event_callback(
            PLACEHOLDER_CREATED_TOPIC, collector.collect
        )
        controller.create_placeholder("fake", {"name": "one"})

        assert len(collector.events) == 1
        assert collector.events[0]["scene_identifier"] == "node_1"

    def test_unknown_plugin_is_reported(self, controller):
        result = controller.create_placeholder("nope", {})
        assert not result.success
        assert "nope" in result.error_title

    def test_failure_is_reported_with_traceback(self, controller):
        _Plugin.fail_on = "create"
        try:
            result = controller.create_placeholder("fake", {"name": "one"})
        finally:
            _Plugin.fail_on = None

        assert not result.success
        assert "create boom" in result.error_detail


class TestUpdateDeleteSelect:
    def test_update_stores_new_values(self, controller):
        identifier = controller.create_placeholder(
            "fake", {"name": "one"}
        ).scene_identifier

        collector = _EventCollector()
        controller.register_event_callback(
            PLACEHOLDER_UPDATED_TOPIC, collector.collect
        )
        result = controller.update_placeholder(identifier, {"name": "two"})

        assert result.success
        assert len(collector.events) == 1
        labels = [item.label for item in controller.get_placeholder_items()]
        assert labels == ["two"]

    def test_delete_removes_placeholder(self, controller):
        identifier = controller.create_placeholder(
            "fake", {"name": "one"}
        ).scene_identifier

        collector = _EventCollector()
        controller.register_event_callback(
            PLACEHOLDER_DELETED_TOPIC, collector.collect
        )
        result = controller.delete_placeholder(identifier)

        assert result.success
        assert len(collector.events) == 1
        assert controller.get_placeholder_items() == []

    def test_select_reaches_the_host(self, controller):
        identifier = controller.create_placeholder(
            "fake", {"name": "one"}
        ).scene_identifier

        assert controller.select_placeholder(identifier).success
        assert controller._builder.scene.selected == [identifier]

    @pytest.mark.parametrize(
        "action", ["update_placeholder", "delete_placeholder",
                   "select_placeholder", "run_placeholder"]
    )
    def test_missing_placeholder_is_reported(self, controller, action):
        method = getattr(controller, action)
        if action == "update_placeholder":
            result = method("gone", {})
        else:
            result = method("gone")

        assert not result.success
        assert "not available" in result.error_title


class TestRunPlaceholder:
    def test_run_reaches_the_host(self, controller):
        identifier = controller.create_placeholder(
            "fake", {"name": "one"}
        ).scene_identifier

        result = controller.run_placeholder(identifier)

        assert result.success
        assert controller._builder.scene.ran == [identifier]


class TestTemplateBuild:
    def test_build_processes_all_placeholders(self, controller):
        controller.create_placeholder("fake", {"name": "one"})
        controller.create_placeholder("fake", {"name": "two"})

        result = controller.run_template_build()

        assert result.success
        assert len(controller._builder.scene.ran) == 2

    def test_build_results_are_stored(self, controller):
        controller.create_placeholder("fake", {"name": "one"})

        controller.run_template_build()

        results = controller.get_last_build_results()
        assert len(results) == 1
        identifier, label, error = results[0]
        assert identifier == "node_1"
        assert label == "one"
        assert error == ""

    def test_build_failure_is_reported(self, controller):
        controller.create_placeholder("fake", {"name": "one"})

        _Plugin.fail_on = "run"
        try:
            result = controller.run_template_build()
        finally:
            _Plugin.fail_on = None

        assert not result.success
        assert "1 placeholder(s) failed" in result.error_title
        assert "run boom" in result.error_detail

        results = controller.get_last_build_results()
        assert "run boom" in results[0][2]

    def test_build_steps_are_recorded(self, controller):
        controller.create_placeholder("fake", {"name": "one"})

        controller.run_template_build()

        steps = controller.get_build_steps()
        assert len(steps) == 1
        step = steps[0]
        assert step.scene_identifier == "node_1"
        assert step.label == "one"
        assert step.status == "succeeded"
        assert step.error == ""
        assert step.duration >= 0

    def test_failed_build_step_is_recorded(self, controller):
        controller.create_placeholder("fake", {"name": "one"})

        _Plugin.fail_on = "run"
        try:
            controller.run_template_build()
        finally:
            _Plugin.fail_on = None

        step = controller.get_build_steps()[0]
        assert step.status == "failed"
        assert "run boom" in step.error

    def test_build_steps_are_copies(self, controller):
        controller.create_placeholder("fake", {"name": "one"})
        controller.run_template_build()

        steps = controller.get_build_steps()
        steps[0].status = "changed"

        assert controller.get_build_steps()[0].status == "succeeded"

    def test_build_history_is_limited(self, controller):
        controller.create_placeholder("fake", {"name": "one"})
        for _ in range(MAX_BUILD_HISTORY + 2):
            controller.run_template_build()

        history = controller.get_build_history()
        assert len(history) == MAX_BUILD_HISTORY
        assert history[-1][0].scene_identifier == "node_1"

    def test_build_log_is_available(self, controller):
        controller.create_placeholder("fake", {"name": "one"})

        controller.run_template_build()

        assert isinstance(controller.get_build_log(), list)

    def test_progress_callback_is_called_per_placeholder(self, controller):
        controller.create_placeholder("fake", {"name": "one"})
        controller.create_placeholder("fake", {"name": "two"})
        progress = []

        controller.run_template_build(
            progress_callback=lambda count, data: progress.append(count)
        )

        assert progress == [1, 2]


class TestTemplateFile:
    @pytest.fixture
    def template_path(self, tmp_path_factory):
        path = tmp_path_factory.mktemp("template") / "template.ma"
        path.write_text("")
        return str(path)

    @staticmethod
    def _set_preset(controller, monkeypatch, preset):
        monkeypatch.setattr(
            controller._builder, "get_template_preset", lambda: preset
        )

    def test_missing_profile_is_reported(self, controller, monkeypatch):
        self._set_preset(controller, monkeypatch, TemplatePreset())

        assert controller.get_template_path() is None
        for result in (
            controller.open_template(),
            controller.build_template(),
        ):
            assert not result.success
            assert "No template" in result.error_title

    def test_template_settings_error_is_reported(
        self, controller, monkeypatch
    ):
        def fail():
            raise RuntimeError("settings boom")

        monkeypatch.setattr(
            controller._builder, "get_template_preset", fail
        )

        result = controller.open_template()

        assert not result.success
        assert "Failed to read the template settings" in result.error_title
        assert "settings boom" in result.error_detail

    def test_missing_file_is_reported(self, controller, monkeypatch):
        self._set_preset(controller, monkeypatch, TemplatePreset(
            path="/does/not/exist.ma", profile={"path": "x"}
        ))

        assert controller.get_template_path() == "/does/not/exist.ma"
        result = controller.build_template()
        assert not result.success
        assert result.error_detail == "/does/not/exist.ma"

    def test_open_template_opens_and_resets(
        self, controller, monkeypatch, template_path
    ):
        preset = TemplatePreset(path=template_path, profile={"path": "x"})
        self._set_preset(controller, monkeypatch, preset)
        opened = []
        monkeypatch.setattr(
            controller._builder, "open_template", opened.append
        )
        events = _EventCollector()
        controller.register_event_callback(
            PLACEHOLDERS_REFRESHED_TOPIC, events.collect
        )
        refresh_count = controller._builder.refresh_count

        result = controller.open_template()

        assert result.success
        assert opened == [preset]
        assert controller._builder.refresh_count == refresh_count + 1
        assert events.events

    def test_build_template_imports_and_populates(
        self, controller, monkeypatch, template_path
    ):
        self._set_preset(controller, monkeypatch, TemplatePreset(
            path=template_path, profile={"path": "x"}
        ))
        imported = []

        def import_template(path):
            imported.append(path)
            controller._builder.scene.add({"name": "from_template"})

        monkeypatch.setattr(
            controller._builder, "import_template", import_template
        )

        result = controller.build_template()

        assert result.success
        assert imported == [template_path]
        assert len(controller.get_placeholder_items()) == 1
        steps = controller.get_build_steps()
        assert len(steps) == 1
        assert steps[0].status == "succeeded"
        assert steps[0].label == "from_template"

    def test_build_from_template_reports_failed_steps(
        self, controller, monkeypatch, template_path
    ):
        self._set_preset(controller, monkeypatch, TemplatePreset(
            path=template_path, profile={"path": "x"}
        ))

        def import_template(path):
            controller._builder.scene.add({"name": "from_template"})

        monkeypatch.setattr(
            controller._builder, "import_template", import_template
        )
        _Plugin.fail_on = "populate"
        try:
            controller.build_template()
        finally:
            _Plugin.fail_on = None

        steps = controller.get_build_steps()
        assert len(steps) == 1
        assert steps[0].status == "failed"
        assert "populate boom" in steps[0].error

    def test_build_failure_is_reported(
        self, controller, monkeypatch, template_path
    ):
        self._set_preset(controller, monkeypatch, TemplatePreset(
            path=template_path, profile={"path": "x"}
        ))

        def import_template(path):
            raise RuntimeError("Broken template")

        monkeypatch.setattr(
            controller._builder, "import_template", import_template
        )

        result = controller.build_template()

        assert not result.success
        assert "Broken template" in result.error_detail

    def test_build_template_captures_log(
        self, controller, monkeypatch, template_path
    ):
        self._set_preset(controller, monkeypatch, TemplatePreset(
            path=template_path, profile={"path": "x"}
        ))

        def build_template(preset=None):
            logging.getLogger(
                "ayon_core.pipeline.workfile.test"
            ).warning("build marker")
            return []

        monkeypatch.setattr(
            controller._builder, "build_template", build_template
        )

        controller.build_template()

        assert any(
            "build marker" in line for line in controller.get_build_log()
        )

    def test_build_failure_refreshes_the_ui(
        self, controller, monkeypatch, template_path
    ):
        self._set_preset(controller, monkeypatch, TemplatePreset(
            path=template_path, profile={"path": "x"}
        ))

        def import_template(path):
            raise RuntimeError("Broken template")

        monkeypatch.setattr(
            controller._builder, "import_template", import_template
        )
        events = _EventCollector()
        controller.register_event_callback(
            PLACEHOLDERS_REFRESHED_TOPIC, events.collect
        )

        result = controller.build_template()

        assert not result.success
        assert events.events


class TestPlaceholderData:
    def test_item_info_carries_plugin_details(self, controller):
        controller.create_placeholder("fake", {"name": "one", "order": 5})
        item = controller.get_placeholder_items()[0]

        assert item.plugin_identifier == "fake"
        assert item.plugin_label == "Fake"
        assert item.label == "one"
        assert item.order == 5
        assert item.icon == _Plugin.icon
        assert item.data["name"] == "one"
        assert item.delete_supported
        assert item.run_supported

    def test_options_use_stored_values_as_defaults(self, controller):
        attr_defs = controller.get_placeholder_options(
            "fake", {"name": "stored"}
        )
        assert attr_defs[0].default == "stored"

    def test_preview_and_completions_reach_the_plugin(self, controller):
        preview = controller.get_placeholder_preview("fake", {"name": "one"})
        assert preview.title == "Preview of one"
        assert controller.get_placeholder_completions("fake", {}) == {
            "name": ["one", "two"]
        }

    def test_dynamic_data_combines_preview_and_completions(
        self, controller
    ):
        data = controller.get_placeholder_dynamic_data(
            "fake", {"name": "one"}
        )

        assert data.preview.title == "Preview of one"
        assert data.completions == {"name": ["one", "two"]}
        assert data.completions_error is None

    def test_dynamic_data_reports_completion_error(self, controller):
        _Plugin.fail_on = "completions"
        try:
            data = controller.get_placeholder_dynamic_data(
                "fake", {"name": "one"}
            )
        finally:
            _Plugin.fail_on = None

        assert data.preview.title == "Preview of one"
        assert "completions boom" in data.completions_error


class TestReset:
    def test_reset_refreshes_the_builder(self, controller):
        collector = _EventCollector()
        controller.register_event_callback(
            "placeholders.refreshed", collector.collect
        )
        controller.reset()

        assert controller._builder.refresh_count == 1
        assert len(collector.events) == 1

    def test_scene_changes_outside_the_tool_are_picked_up(self, controller):
        controller.create_placeholder("fake", {"name": "one"})
        assert len(controller.get_placeholder_items()) == 1

        controller._builder.scene.add({"name": "added elsewhere"})
        controller.reset()

        labels = sorted(
            item.label for item in controller.get_placeholder_items()
        )
        assert labels == ["added elsewhere", "one"]


class _WorkfileHost:
    """Host stand-in with a saved workfile."""

    def get_current_workfile(self):
        return "/work/library/modeling_template.ma"


class TestBuildContext:
    @pytest.fixture(autouse=True)
    def _host_context(self, monkeypatch):
        monkeypatch.setenv("AYON_FOLDER_PATH", "/assets/bob")
        monkeypatch.setenv("AYON_TASK_NAME", "modeling")

    def test_host_context_is_used_by_default(self, controller):
        context_item = controller.get_build_context()

        assert context_item.folder_path == "/assets/bob"
        assert context_item.task_name == "modeling"
        assert not context_item.is_override
        assert context_item.label == "/assets/bob \u00b7 modeling"

    def test_chosen_context_is_used(self, controller):
        collector = _EventCollector()
        controller.register_event_callback(
            BUILD_CONTEXT_CHANGED_TOPIC, collector.collect
        )
        controller.set_build_context("/shots/sh010", "animation")

        context_item = controller.get_build_context()
        assert context_item.folder_path == "/shots/sh010"
        assert context_item.task_name == "animation"
        assert context_item.is_override
        assert controller._builder.current_folder_path == "/shots/sh010"
        assert len(collector.events) == 1

    def test_chosen_context_survives_reset(self, controller):
        controller.set_build_context("/shots/sh010", "animation")
        controller.reset()

        assert controller.get_build_context().is_override

    def test_host_context_is_used_again(self, controller):
        controller.set_build_context("/shots/sh010", "animation")
        controller.set_build_context(None)

        context_item = controller.get_build_context()
        assert not context_item.is_override
        assert context_item.folder_path == "/assets/bob"

    def test_invalid_folder_is_rejected(self, controller, monkeypatch):
        monkeypatch.setattr(
            wtb, "get_folder_by_path", lambda *args: None
        )

        result = controller.set_build_context("/missing", "animation")

        assert not result.success
        assert "not found" in result.error_detail
        assert controller._builder.get_context_override() is None

    def test_invalid_task_restores_previous_context(
        self, controller, monkeypatch
    ):
        controller.set_build_context("/shots/sh010", "animation")
        monkeypatch.setattr(
            wtb, "get_task_by_name", lambda *args: None
        )

        result = controller.set_build_context("/shots/sh020", "missing")

        assert not result.success
        assert "not found" in result.error_detail
        assert controller._builder.get_context_override() == (
            "/shots/sh010",
            "animation",
        )

    def test_context_item_label(self):
        context_item = BuildContextItem("/shots/sh010", None, True)

        assert context_item.label == "/shots/sh010"


class TestWorkfileName:
    def test_name_of_saved_workfile(self):
        controller = WorkfileTemplateBuilderController(
            _Builder(_WorkfileHost())
        )
        assert controller.get_workfile_name() == "modeling_template.ma"

    def test_host_without_workfiles(self, controller):
        assert controller.get_workfile_name() is None

    def test_without_builder(self):
        controller = WorkfileTemplateBuilderController(None)
        assert controller.get_workfile_name() is None
        assert controller.get_build_context().label == "No context"


class TestPlaceholderCollectionErrors:
    def test_failed_collection_is_reported_and_retried(self, controller):
        _Plugin.fail_on = "collect"
        try:
            items = controller.get_placeholder_items()
        finally:
            _Plugin.fail_on = None

        assert items == []
        error = controller.get_placeholders_error()
        assert error is not None
        assert "fake" in error
        assert "collect boom" in error

        # The failed collection must not be cached.
        controller._builder.scene.add({"name": "one"})
        labels = [item.label for item in controller.get_placeholder_items()]
        assert labels == ["one"]
        assert controller.get_placeholders_error() is None


class TestPlaceholderPluginErrors:
    def test_options_failure_is_raised(self, controller):
        _Plugin.fail_on = "options"
        try:
            with pytest.raises(PlaceholderOptionsError) as exc_info:
                controller.get_placeholder_options("fake")
        finally:
            _Plugin.fail_on = None

        assert "options boom" in str(exc_info.value)

    def test_completions_failure_is_raised(self, controller):
        _Plugin.fail_on = "completions"
        try:
            with pytest.raises(PlaceholderCompletionsError) as exc_info:
                controller.get_placeholder_completions(
                    "fake", {"name": "one"}
                )
        finally:
            _Plugin.fail_on = None

        assert "completions boom" in str(exc_info.value)


class TestRunSupport:
    def test_run_placeholder_falls_back_to_populate(
        self, controller, monkeypatch
    ):
        identifier = controller.create_placeholder(
            "fake", {"name": "one"}
        ).scene_identifier
        monkeypatch.setattr(
            _Plugin,
            "repopulate_placeholder",
            PlaceholderPlugin.repopulate_placeholder,
        )

        result = controller.run_placeholder(identifier)

        assert result.success
        assert controller._builder.scene.populated == [identifier]
        assert controller._builder.scene.ran == []

    def test_run_all_falls_back_to_populate(
        self, controller, monkeypatch
    ):
        controller.create_placeholder("fake", {"name": "one"})
        monkeypatch.setattr(
            _Plugin,
            "repopulate_placeholder",
            PlaceholderPlugin.repopulate_placeholder,
        )

        result = controller.run_template_build()

        steps = controller.get_build_steps()
        assert result.success
        assert [step.status for step in steps] == ["succeeded"]
        assert controller._builder.scene.populated == ["node_1"]
        assert controller._builder.scene.ran == []


class TestBuilderEventBinding:
    def test_durations_are_recorded_after_reset(self, controller):
        controller.create_placeholder("fake", {"name": "one"})
        controller.reset()

        controller.run_template_build()

        steps = controller.get_build_steps()
        assert steps
        assert steps[0].duration > 0

    def test_plugin_item_error_is_reported_by_run(self, controller):
        identifier = controller.create_placeholder(
            "fake", {"name": "one"}
        ).scene_identifier
        _Plugin.fail_on = "run_error"
        try:
            result = controller.run_placeholder(identifier)
        finally:
            _Plugin.fail_on = None

        assert not result.success
        assert "run error" in result.error_detail


class TestFailedActionInvalidation:
    def test_partial_create_is_visible_after_failure(self, controller):
        _Plugin.fail_on = "create_partial"
        try:
            result = controller.create_placeholder("fake", {"name": "one"})
        finally:
            _Plugin.fail_on = None

        assert not result.success
        assert len(controller.get_placeholder_items()) == 1

    def test_partial_update_is_visible_after_failure(self, controller):
        identifier = controller.create_placeholder(
            "fake", {"name": "one"}
        ).scene_identifier
        _Plugin.fail_on = "update_partial"
        try:
            result = controller.update_placeholder(
                identifier, {"name": "changed"}
            )
        finally:
            _Plugin.fail_on = None

        assert not result.success
        items = controller.get_placeholder_items()
        assert items[0].data["name"] == "changed"

    def test_partial_delete_is_visible_after_failure(self, controller):
        identifier = controller.create_placeholder(
            "fake", {"name": "one"}
        ).scene_identifier
        _Plugin.fail_on = "delete_partial"
        try:
            result = controller.delete_placeholder(identifier)
        finally:
            _Plugin.fail_on = None

        assert not result.success
        assert controller.get_placeholder_items() == []


class TestRenamedPlaceholder:
    def test_update_resolves_renamed_scene_identifier(
        self, controller, monkeypatch
    ):
        identifier = controller.create_placeholder(
            "fake", {"name": "one"}
        ).scene_identifier

        def rename_update(plugin, placeholder_item, placeholder_data):
            plugin.scene.nodes.pop(placeholder_item.scene_identifier)
            plugin.scene.nodes["renamed"] = dict(placeholder_data)

        monkeypatch.setattr(_Plugin, "update_placeholder", rename_update)

        result = controller.update_placeholder(
            identifier, {"name": "renamed"}
        )

        assert result.success
        assert result.scene_identifier == "renamed"
        assert "renamed" in controller._builder.scene.nodes


class TestCapabilityGuards:
    def test_delete_requires_plugin_support(
        self, controller, monkeypatch
    ):
        identifier = controller.create_placeholder(
            "fake", {"name": "one"}
        ).scene_identifier
        monkeypatch.setattr(
            _Plugin,
            "delete_placeholder",
            PlaceholderPlugin.delete_placeholder,
        )

        result = controller.delete_placeholder(identifier)

        assert not result.success
        assert "not supported" in result.error_title
        assert identifier in controller._builder.scene.nodes

    def test_select_requires_plugin_support(
        self, controller, monkeypatch
    ):
        identifier = controller.create_placeholder(
            "fake", {"name": "one"}
        ).scene_identifier
        monkeypatch.setattr(
            _Plugin,
            "select_placeholder",
            PlaceholderPlugin.select_placeholder,
        )

        result = controller.select_placeholder(identifier)

        assert not result.success
        assert "not supported" in result.error_title
        assert controller._builder.scene.selected == []


class TestHostEvents:
    def test_task_changed_resets_the_controller(self, controller):
        from ayon_core.lib import emit_event

        before = controller._builder.refresh_count
        emit_event("taskChanged", {})

        assert controller._builder.refresh_count == before + 1

    def test_closed_controller_stops_listening(self, controller):
        from ayon_core.lib import emit_event

        controller.close()
        before = controller._builder.refresh_count
        emit_event("taskChanged", {})

        assert controller._builder.refresh_count == before

    def test_project_change_clears_context_override(
        self, controller, monkeypatch
    ):
        from ayon_core.lib import emit_event
        from ayon_core.tools.workfile_template_build import control

        controller.set_build_context("/shots/sh010", "animation")
        assert controller._builder.get_context_override() is not None
        monkeypatch.setattr(
            control, "get_current_project_name", lambda: "other_project"
        )

        emit_event("taskChanged", {})

        assert controller._builder.get_context_override() is None
