"""Tests for the workfile template builder tool window."""
from __future__ import annotations

import pytest
from qtpy import QtWidgets

from ayon_core.lib import attribute_definitions
from ayon_core.pipeline.workfile.workfile_template_builder import (
    AbstractTemplateBuilder,
    PlaceholderItem,
    PlaceholderPlugin,
    PlaceholderPreview,
    PlaceholderPreviewItem,
)
from ayon_core.tools.workfile_template_build import (
    WorkfileTemplateBuilderController,
    WorkfileTemplateBuilderWindow,
)

HINT_PAGE = 0
EDITOR_PAGE = 1


class _Plugin(PlaceholderPlugin):
    label = "Fake"
    identifier = "fake"
    icon = {"type": "material-symbols", "name": "download", "color": "#fff"}

    def __init__(self, builder):
        super().__init__(builder)
        self.nodes = builder.nodes

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
        return PlaceholderPreview(
            title="Would load 1 representation",
            items=[PlaceholderPreviewItem("/assets/bob", "v001 - ma")],
        )

    def get_placeholder_completions(self, placeholder_data):
        return {"name": ["one", "two"]}

    def create_placeholder(self, placeholder_data):
        # Returns nothing on purpose, like some host implementations
        identifier = "node_{}".format(len(self.nodes) + 1)
        self.nodes[identifier] = dict(placeholder_data)

    def update_placeholder(self, placeholder_item, placeholder_data):
        self.nodes[placeholder_item.scene_identifier] = dict(
            placeholder_data
        )

    def collect_placeholders(self):
        return [
            PlaceholderItem(identifier, dict(data), self)
            for identifier, data in self.nodes.items()
        ]

    def populate_placeholder(self, placeholder):
        pass

    def delete_placeholder(self, placeholder_item):
        self.nodes.pop(placeholder_item.scene_identifier, None)


class _Builder(AbstractTemplateBuilder):
    def __init__(self, host=None):
        super().__init__(host)
        self.nodes = {}

    def get_placeholder_plugin_classes(self):
        return [_Plugin]

    def import_template(self, path):
        return True


class _Answers:
    """Queue of answers for 'QMessageBox.question'."""

    def __init__(self):
        self.queue = []

    def question(self, *args, **kwargs):
        return self.queue.pop(0)


@pytest.fixture
def answers(monkeypatch):
    output = _Answers()
    monkeypatch.setattr(
        QtWidgets.QMessageBox, "question", staticmethod(output.question)
    )
    return output


@pytest.fixture
def builder():
    return _Builder(None)


@pytest.fixture
def window(qtbot, builder):
    controller = WorkfileTemplateBuilderController(builder)
    output = WorkfileTemplateBuilderWindow(controller)
    qtbot.addWidget(output)
    output.show()
    qtbot.waitExposed(output)
    return output


def _name_input(window):
    attrs_widget = window._editor_widget._attrs_widget
    return attrs_widget._widgets_by_key["name"]._input_widget


class TestFirstShow:
    def test_hint_page_is_shown_without_placeholders(self, window):
        assert window._pages_widget.currentIndex() == HINT_PAGE

    def test_host_without_builder_cannot_create(self, qtbot):
        controller = WorkfileTemplateBuilderController(None)
        window = WorkfileTemplateBuilderWindow(controller)
        qtbot.addWidget(window)
        window.show()
        qtbot.waitExposed(window)

        window._on_create_request()

        assert window._pages_widget.currentIndex() == HINT_PAGE
        assert window._hint_widget._create_btn.isHidden()


class TestCreate:
    def test_created_placeholder_is_listed_and_selected(
        self, window, builder
    ):
        window._on_create_request()
        assert window._pages_widget.currentIndex() == EDITOR_PAGE

        window._on_create_confirmed("fake", {"name": "one"})

        assert list(builder.nodes) == ["node_1"]
        assert window._pages_widget.currentIndex() == EDITOR_PAGE
        assert window._current_identifier == "node_1"
        assert (
            window._placeholders_widget.get_selected_identifier() == "node_1"
        )

    def test_cancel_returns_to_hint_page(self, window, builder):
        window._on_create_request()
        window._on_create_cancelled()

        assert window._pages_widget.currentIndex() == HINT_PAGE
        assert builder.nodes == {}


class TestEdit:
    @pytest.fixture(autouse=True)
    def _placeholders(self, window):
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "two"})
        window._select_silently("node_1")
        window._show_editor_page("node_1")

    def test_preview_and_completions_are_shown(self, window):
        editor = window._editor_widget
        editor._on_dynamic_timer()

        preview = editor._preview_widget
        assert preview._title_label.text() == "Would load 1 representation"
        assert preview._items_model.rowCount() == 1
        completer = _name_input(window).completer()
        assert completer.model().stringList() == ["one", "two"]

    def test_save_updates_scene_and_list(self, window, builder):
        window._on_save_confirmed("node_1", {"name": "renamed"})

        assert builder.nodes["node_1"] == {"name": "renamed"}
        labels = sorted(
            item.label for item in window._placeholder_items_by_id.values()
        )
        assert labels == ["renamed", "two"]

    def test_cancelled_discard_keeps_selection_and_changes(
        self, window, answers
    ):
        _name_input(window).setText("changed")
        assert window._editor_widget.has_unsaved_changes()

        answers.queue.append(QtWidgets.QMessageBox.Cancel)
        window._placeholders_widget.select_identifier("node_2")

        assert answers.queue == []
        assert window._current_identifier == "node_1"
        assert (
            window._placeholders_widget.get_selected_identifier() == "node_1"
        )
        assert window._editor_widget.has_unsaved_changes()

    def test_discard_switches_placeholder(self, window, builder, answers):
        _name_input(window).setText("changed")

        answers.queue.append(QtWidgets.QMessageBox.Discard)
        window._placeholders_widget.select_identifier("node_2")

        assert window._current_identifier == "node_2"
        assert builder.nodes["node_1"] == {"name": "one"}

    def test_revert_restores_stored_values(self, window):
        _name_input(window).setText("changed")
        window._editor_widget._on_cancel_click()

        assert not window._editor_widget.has_unsaved_changes()
        assert _name_input(window).text() == "one"

    def test_placeholder_removed_outside_of_tool(self, window, builder):
        builder.nodes.pop("node_1")
        window.refresh()

        assert window._pages_widget.currentIndex() == HINT_PAGE

    def test_delete_asks_for_confirmation(self, window, builder, answers):
        answers.queue.append(QtWidgets.QMessageBox.No)
        window._on_delete_request()
        assert "node_1" in builder.nodes

        answers.queue.append(QtWidgets.QMessageBox.Yes)
        window._on_delete_request()
        assert "node_1" not in builder.nodes
        assert window._pages_widget.currentIndex() == HINT_PAGE

    def test_filter_matches_label_and_type(self, window):
        widget = window._placeholders_widget
        widget._filter_input.setText("two")
        assert widget._proxy_model.rowCount() == 1

        widget._filter_input.setText("fake")
        assert widget._proxy_model.rowCount() == 2

        widget._filter_input.setText("nothing")
        assert widget._proxy_model.rowCount() == 0
