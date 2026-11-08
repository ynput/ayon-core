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
from ayon_core.tools.workfile_template_build.ui.build_report import (
    BuildReportDialog,
)
from ayon_core.tools.workfile_template_build.ui.placeholders_widget import (
    LABEL_COLUMN,
    UNSAVED_MARK,
)

HINT_PAGE = 0
EDITOR_PAGE = 1


class _Plugin(PlaceholderPlugin):
    label = "Fake"
    identifier = "fake"
    icon = {"type": "material-symbols", "name": "download", "color": "#fff"}

    # Set by tests to make an action fail
    fail_on = None

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

    def repopulate_placeholder(self, placeholder):
        if self.fail_on == "run":
            raise RuntimeError("run boom")
        self.builder.runs.append(placeholder.scene_identifier)


class _Builder(AbstractTemplateBuilder):
    def __init__(self, host=None):
        super().__init__(host)
        self.nodes = {}
        self.runs = []

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
        assert window._hint_widget._steps_widget.isHidden()
        assert window._hint_widget._pointer_widget.isHidden()
        assert not window._context_bar._context_btn.isEnabled()

    def test_add_button_is_enabled_with_placeholder_types(self, window):
        assert window._placeholders_widget._create_btn.isEnabled()

    def test_empty_list_is_replaced_by_message(self, window):
        placeholders_widget = window._placeholders_widget
        assert placeholders_widget._view.isHidden()
        assert not placeholders_widget._empty_widget.isHidden()

    def test_list_is_shown_with_placeholders(self, window):
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})

        placeholders_widget = window._placeholders_widget
        assert not placeholders_widget._view.isHidden()
        assert placeholders_widget._empty_widget.isHidden()


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

    def test_create_placeholder_of_requested_type(self, window, builder):
        window._on_create_request("fake")
        assert window._pages_widget.currentIndex() == EDITOR_PAGE

        window._editor_widget._on_confirm_click()

        assert list(builder.nodes) == ["node_1"]

    def test_unknown_type_is_ignored(self, window):
        window._on_create_request("unknown")

        assert window._pages_widget.currentIndex() == HINT_PAGE

    def test_cancel_returns_to_hint_page(self, window, builder):
        window._on_create_request()
        window._on_create_cancelled()

        assert window._pages_widget.currentIndex() == HINT_PAGE
        assert builder.nodes == {}


def _list_labels(window):
    model = window._placeholders_widget._model
    return sorted(
        model.item(row, LABEL_COLUMN).text()
        for row in range(model.rowCount())
    )


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

    def test_unsaved_changes_are_shown(self, window):
        editor = window._editor_widget
        _name_input(window).setText("changed")

        assert not editor._unsaved_label.isHidden()
        assert _list_labels(window) == sorted([UNSAVED_MARK + "one", "two"])

        editor._on_cancel_click()

        assert editor._unsaved_label.isHidden()
        assert _list_labels(window) == ["one", "two"]

    def test_unsaved_mark_survives_list_refresh(self, window):
        _name_input(window).setText("changed")
        window._update_placeholders()

        assert _list_labels(window) == sorted([UNSAVED_MARK + "one", "two"])

    def test_placeholder_removed_outside_of_tool(self, window, builder):
        builder.nodes.pop("node_1")
        window.refresh()

        assert window._pages_widget.currentIndex() == HINT_PAGE

    def test_remove_deletes_placeholder_without_confirmation(
        self, window, builder
    ):
        window._on_remove_request()

        assert "node_1" not in builder.nodes
        assert window._pages_widget.currentIndex() == HINT_PAGE

    def test_header_shows_label_and_scene_identifier(self, window):
        editor = window._editor_widget
        assert editor._header_widget._title_label.text() == "one"
        assert editor._header_widget._subtitle_label.text() == "Fake - node_1"

    def test_header_does_not_repeat_scene_identifier(self, window):
        # Label of the placeholder is the same as its scene identifier
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "node_3"})

        editor = window._editor_widget
        assert editor._header_widget._title_label.text() == "node_3"
        assert editor._header_widget._subtitle_label.text() == "Fake"

    def test_select_in_scene_is_disabled_when_not_supported(self, window):
        select_btn = window._editor_widget._select_btn
        assert not select_btn.isHidden()
        assert not select_btn.isEnabled()

    def test_placeholders_are_listed_in_build_order(self, window, builder):
        builder.nodes["node_1"]["order"] = 20
        builder.nodes["node_2"]["order"] = 10
        window.refresh()

        proxy_model = window._placeholders_widget._proxy_model
        labels = [
            proxy_model.index(row, 1).data()
            for row in range(proxy_model.rowCount())
        ]
        assert labels == ["two", "one"]

    def test_filter_matches_label_and_type(self, window):
        widget = window._placeholders_widget
        widget._filter_input.setText("two")
        assert widget._proxy_model.rowCount() == 1

        widget._filter_input.setText("fake")
        assert widget._proxy_model.rowCount() == 2

        widget._filter_input.setText("nothing")
        assert widget._proxy_model.rowCount() == 0


class TestEditorActions:
    def test_actions_are_hidden_in_create_mode(self, window):
        window._on_create_request()

        editor = window._editor_widget
        assert not editor._run_btn.isVisible()
        assert not editor._remove_btn.isVisible()

    def test_actions_are_enabled_in_edit_mode(self, window):
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})

        editor = window._editor_widget
        assert editor._run_btn.isVisible()
        assert editor._run_btn.isEnabled()
        assert editor._remove_btn.isVisible()
        assert editor._remove_btn.isEnabled()

    def test_actions_are_next_to_the_name(self, window):
        window.resize(1200, 600)
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})

        assert not window._editor_widget._header_widget.are_actions_below()

    def test_actions_move_below_a_long_name(self, window):
        window.resize(1200, 600)
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "a" * 120})

        assert window._editor_widget._header_widget.are_actions_below()

    def test_run_button_runs_the_placeholder(self, window, builder):
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})

        window._editor_widget._run_btn.click()

        assert builder.runs == ["node_1"]

    def test_remove_button_removes_the_placeholder(self, window, builder):
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})

        window._editor_widget._remove_btn.click()

        assert "node_1" not in builder.nodes
        assert window._pages_widget.currentIndex() == HINT_PAGE


class TestBuild:
    def test_build_button_is_disabled_without_placeholders(self, window):
        assert not window._context_bar._test_build_btn.isEnabled()

    def test_build_button_is_enabled_with_placeholders(self, window):
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})

        assert window._context_bar._test_build_btn.isEnabled()

    def test_build_asks_for_confirmation(self, window, builder, answers):
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})
        builder.runs.clear()

        answers.queue.append(QtWidgets.QMessageBox.No)
        window._on_run_template_build_request()
        assert builder.runs == []

        answers.queue.append(QtWidgets.QMessageBox.Yes)
        window._on_run_template_build_request()
        assert builder.runs == ["node_1"]

    def test_build_reports_processed_placeholders(self, window, answers):
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})

        answers.queue.append(QtWidgets.QMessageBox.Yes)
        window._on_run_template_build_request()

        status_btn = window._build_status_btn
        assert status_btn.isVisible()
        assert status_btn.text() == "1 populated"
        assert "[OK]" in status_btn.toolTip()

    def test_build_reports_failed_placeholder(self, window, answers):
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})

        _Plugin.fail_on = "run"
        try:
            answers.queue.append(QtWidgets.QMessageBox.Yes)
            window._on_run_template_build_request()
        finally:
            _Plugin.fail_on = None

        status_btn = window._build_status_btn
        assert status_btn.isVisible()
        assert status_btn.text() == "1 of 1 failed"
        assert "run boom" in status_btn.toolTip()

    def test_build_status_is_hidden_before_build(self, window):
        assert window._build_status_btn.isHidden()


class TestBuildReport:
    """Report dialog of the last build."""

    def test_build_report_lists_steps(self, window):
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})
        window._controller.run_template_build()

        dialog = BuildReportDialog(window._controller, parent=window)
        try:
            assert dialog._model.rowCount() == 1
            assert dialog._model.item(0, 1).text() == "one"
            assert dialog._model.item(0, 2).text() == "OK"
            assert "1 placeholder(s) processed" in dialog.get_report_text()
        finally:
            dialog.close()

    def test_build_report_shows_failure(self, window):
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})

        _Plugin.fail_on = "run"
        try:
            window._controller.run_template_build()
        finally:
            _Plugin.fail_on = None

        dialog = BuildReportDialog(window._controller, parent=window)
        try:
            assert dialog._model.item(0, 2).text() == "FAILED"
            assert "run boom" in dialog.get_report_text()
        finally:
            dialog.close()


class TestGuide:
    def test_guide_points_to_add_without_placeholders(self, window):
        guide = window._hint_widget

        assert not guide._pointer_widget.isHidden()
        assert guide._steps_widget.get_states() == [
            "active", "todo", "todo"
        ]

    def test_guide_moves_on_with_placeholders(self, window):
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})
        window._select_silently(None)
        window._show_hint_page()

        guide = window._hint_widget
        assert guide._pointer_widget.isHidden()
        assert guide._steps_widget.get_states() == [
            "done", "active", "todo"
        ]

    def test_add_is_highlighted_without_placeholders(self, window):
        add_btn = window._placeholders_widget._create_btn
        assert add_btn.is_highlighted()

    def test_add_is_not_highlighted_while_creating(self, window):
        window._on_create_request()

        add_btn = window._placeholders_widget._create_btn
        assert not add_btn.is_highlighted()

    def test_add_is_not_highlighted_with_placeholders(self, window):
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})
        window._select_silently(None)
        window._show_hint_page()

        add_btn = window._placeholders_widget._create_btn
        assert not add_btn.is_highlighted()


class TestContextBar:
    def test_unsaved_scene_is_shown(self, window):
        label = window._context_bar._workfile_label
        assert label.text() == "Unsaved scene"

    def test_chosen_context_is_shown(self, window, monkeypatch):
        monkeypatch.setattr(
            window,
            "_ask_for_build_context",
            lambda: ("/shots/sh010", "animation"),
        )
        window._on_context_change_request()

        context_bar = window._context_bar
        assert context_bar._context_btn.text() == (
            "/shots/sh010 \u00b7 animation"
        )
        assert not context_bar._reset_btn.isHidden()
        preview = window._editor_widget._preview_widget
        assert "/shots/sh010" in preview._context_label.text()

    def test_cancelled_context_dialog_changes_nothing(
        self, window, monkeypatch
    ):
        monkeypatch.setattr(window, "_ask_for_build_context", lambda: None)
        window._on_context_change_request()

        assert not window._controller.get_build_context().is_override

    def test_reset_uses_scene_context(self, window):
        window._controller.set_build_context("/shots/sh010", "animation")
        window._on_context_reset_request()

        assert not window._controller.get_build_context().is_override
        assert window._context_bar._reset_btn.isHidden()

    def test_context_change_recalculates_preview(self, window):
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})
        editor = window._editor_widget
        editor._on_dynamic_timer()
        assert editor._last_dynamic_values is not None

        window._controller.set_build_context("/shots/sh010", None)

        assert editor._last_dynamic_values is None
        assert editor._dynamic_timer.isActive()


class TestTemplateMenu:
    @pytest.fixture
    def calls(self, window, monkeypatch):
        from ayon_core.tools.workfile_template_build import ActionResult

        output = []
        controller = window._controller
        monkeypatch.setattr(
            controller, "get_template_path", lambda: "/templates/shot.ma"
        )
        for name in ("open_template", "build_template"):
            monkeypatch.setattr(
                controller,
                name,
                lambda name=name: (
                    output.append(name) or ActionResult(success=True)
                ),
            )
        window._update_template_path()
        return output

    def test_actions_disabled_without_template(self, window):
        context_bar = window._context_bar
        # The button stays enabled so the menu can say why
        assert context_bar._template_btn.isEnabled()
        assert context_bar._template_missing_action.isVisible()
        assert not any(
            action.isEnabled() for action in context_bar._template_actions
        )

    def test_actions_enabled_with_template(self, window, calls):
        context_bar = window._context_bar
        assert not context_bar._template_missing_action.isVisible()
        assert all(
            action.isEnabled() for action in context_bar._template_actions
        )
        assert "/templates/shot.ma" in context_bar._template_btn.toolTip()

    @pytest.mark.parametrize(
        "callback, action",
        [
            ("_on_open_template_request", "open_template"),
            ("_on_build_from_template_request", "build_template"),
        ],
    )
    def test_actions_ask_for_confirmation(
        self, window, calls, answers, callback, action
    ):
        answers.queue.append(QtWidgets.QMessageBox.No)
        getattr(window, callback)()
        assert calls == []

        answers.queue.append(QtWidgets.QMessageBox.Yes)
        getattr(window, callback)()
        assert calls == [action]


class TestSelectPlaceholder:
    def test_placeholder_is_selected_and_shown(self, window):
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "two"})

        assert window.select_placeholder("node_1")
        assert window._pages_widget.currentIndex() == EDITOR_PAGE
        assert window._editor_widget.get_scene_identifier() == "node_1"
        assert (
            window._placeholders_widget.get_selected_identifier() == "node_1"
        )

    def test_unknown_placeholder_is_ignored(self, window):
        assert not window.select_placeholder("missing")
        assert window._pages_widget.currentIndex() == HINT_PAGE
