"""Tests for the workfile template builder tool controller."""
import pytest

from ayon_core.lib import attribute_definitions
from ayon_core.pipeline.workfile.workfile_template_builder import (
    AbstractTemplateBuilder,
    PlaceholderItem,
    PlaceholderPlugin,
    PlaceholderPreview,
)
from ayon_core.tools.workfile_template_build.abstract import (
    PLACEHOLDER_CREATED_TOPIC,
    PLACEHOLDER_DELETED_TOPIC,
    PLACEHOLDER_UPDATED_TOPIC,
)
from ayon_core.tools.workfile_template_build.control import (
    WorkfileTemplateBuilderController,
)


class _FakeScene:
    """Scene stand-in shared by the plugin and the tests."""

    def __init__(self):
        self.nodes = {}
        self.selected = []
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
        return {"name": ["one", "two"]}

    def create_placeholder(self, placeholder_data):
        if self.fail_on == "create":
            raise RuntimeError("create boom")
        # Returns nothing on purpose, like some host implementations
        self.scene.add(placeholder_data)

    def update_placeholder(self, placeholder_item, placeholder_data):
        self.scene.nodes[placeholder_item.scene_identifier] = dict(
            placeholder_data
        )

    def collect_placeholders(self):
        return [
            PlaceholderItem(identifier, dict(data), self)
            for identifier, data in self.scene.nodes.items()
        ]

    def populate_placeholder(self, placeholder):
        pass

    def delete_placeholder(self, placeholder_item):
        self.scene.nodes.pop(placeholder_item.scene_identifier, None)

    def select_placeholder(self, placeholder_item):
        self.scene.selected = [placeholder_item.scene_identifier]


class _ReadOnlyPlugin(_Plugin):
    """Plugin without delete and select support."""
    label = "Read only"
    identifier = "fake.readonly"

    delete_placeholder = PlaceholderPlugin.delete_placeholder
    select_placeholder = PlaceholderPlugin.select_placeholder

    def collect_placeholders(self):
        return []


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
    return WorkfileTemplateBuilderController(_Builder(None))


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
        assert not items_by_id["fake.readonly"].delete_supported
        assert not items_by_id["fake.readonly"].select_supported

    def test_items_are_sorted_by_label(self, controller):
        labels = [
            item.label for item in controller.get_placeholder_plugin_items()
        ]
        assert labels == sorted(labels)


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
                   "select_placeholder"]
    )
    def test_missing_placeholder_is_reported(self, controller, action):
        method = getattr(controller, action)
        if action == "update_placeholder":
            result = method("gone", {})
        else:
            result = method("gone")

        assert not result.success
        assert "not available" in result.error_title


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

    def test_item_info_is_serializable(self, controller):
        controller.create_placeholder("fake", {"name": "one"})
        item = controller.get_placeholder_items()[0]

        assert type(item).from_data(item.to_data()) == item

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
