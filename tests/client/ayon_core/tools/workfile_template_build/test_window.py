"""Tests for the workfile template builder tool window."""
from __future__ import annotations

import pytest
from qtpy import QtCore, QtWidgets

from ayon_core.lib import attribute_definitions
from ayon_core.pipeline.workfile.workfile_template_builder import (
    AbstractTemplateBuilder,
    PlaceholderItem,
    PlaceholderPlugin,
    PlaceholderPreview,
    PlaceholderPreviewItem,
)
from ayon_core.tools.workfile_template_build import (
    ActionResult,
    WorkfileTemplateBuilderController,
    WorkfileTemplateBuilderWindow,
)
from ayon_core.tools.workfile_template_build.abstract import (
    BuildContextItem,
)
from ayon_core.tools.workfile_template_build.ui.build_report import (
    BuildReportDialog,
)
from ayon_core.tools.workfile_template_build.ui.placeholders_widget import (
    LABEL_COLUMN,
    ORDER_COLUMN,
    TYPE_COLUMN,
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
        return PlaceholderPreview(
            title="Would load 1 representation",
            items=[PlaceholderPreviewItem("/assets/bob", "v001 - ma")],
        )

    def get_placeholder_completions(self, placeholder_data):
        if self.fail_on == "completions":
            raise RuntimeError("completions boom")
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
        if self.fail_on == "collect":
            raise RuntimeError("collect boom")
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
        if not self.queue:
            # Closing a window at test teardown must not open a modal dialog.
            return QtWidgets.QMessageBox.Discard
        return self.queue.pop(0)


@pytest.fixture(autouse=True)
def _close_without_prompt(monkeypatch):
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        staticmethod(
            lambda *args, **kwargs: QtWidgets.QMessageBox.Discard
        ),
    )


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

    def test_new_placeholder_is_shown_in_list(self, window):
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})
        window._on_create_request()

        placeholders_widget = window._placeholders_widget
        assert _list_labels(window) == ["New placeholder", "one"]
        # The new placeholder is selected, it has no scene identifier yet
        assert placeholders_widget._view.selectionModel().hasSelection()
        assert placeholders_widget.get_selected_identifier() is None
        # It does not count as a placeholder of the scene
        assert placeholders_widget._count_label.text() == "1"

    def test_new_placeholder_row_is_removed_on_cancel(self, window):
        window._on_create_request()
        assert _list_labels(window) == ["New placeholder"]

        window._on_create_cancelled()

        assert _list_labels(window) == []
        assert window._placeholders_widget._empty_widget.isVisibleTo(window)

    def test_new_placeholder_row_is_replaced_on_create(self, window):
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})

        assert _list_labels(window) == ["one"]

    def test_new_placeholder_row_is_removed_on_other_selection(
        self, window
    ):
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})
        window._on_create_request()

        window._placeholders_widget.select_identifier("node_1")

        assert window._current_identifier == "node_1"
        assert _list_labels(window) == ["one"]


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

    def test_remove_asks_for_confirmation(self, window, builder, answers):
        answers.queue.append(QtWidgets.QMessageBox.No)
        window._on_remove_request()

        assert "node_1" in builder.nodes
        assert window._pages_widget.currentIndex() == EDITOR_PAGE

        answers.queue.append(QtWidgets.QMessageBox.Yes)
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

    def test_remove_button_removes_the_placeholder(
        self, window, builder, answers
    ):
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})

        answers.queue.append(QtWidgets.QMessageBox.Yes)
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
            assert "1 populated" in dialog.get_report_text()
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
        label = "/shots/sh010 \u00b7 animation"
        assert label in context_bar._context_btn.toolTip()
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
                lambda name=name, **kwargs: (
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


class TestOptionsErrors:
    def test_failed_options_are_shown_and_disable_confirm(self, window):
        _Plugin.fail_on = "options"
        try:
            window._on_create_request("fake")
        finally:
            _Plugin.fail_on = None

        editor = window._editor_widget
        assert not editor._options_error_widget.isHidden()
        assert editor._attrs_widget is None
        assert not editor._confirm_btn.isEnabled()
        assert "options boom" in editor._options_error_label.text()

    def test_retry_loads_options(self, window):
        _Plugin.fail_on = "options"
        try:
            window._on_create_request("fake")
        finally:
            _Plugin.fail_on = None

        editor = window._editor_widget
        editor._on_options_retry()

        assert editor._options_error_widget.isHidden()
        assert editor._attrs_widget is not None
        assert editor._confirm_btn.isEnabled()


class TestCollectionErrors:
    def test_error_banner_and_hint_are_shown(self, window):
        _Plugin.fail_on = "collect"
        try:
            window.refresh()
        finally:
            _Plugin.fail_on = None

        placeholders_widget = window._placeholders_widget
        assert not placeholders_widget._error_widget.isHidden()
        assert "collect boom" in placeholders_widget._error_label.text()
        assert placeholders_widget._empty_widget.isHidden()
        assert window._pages_widget.currentIndex() == HINT_PAGE
        assert (
            "Could not read placeholders"
            in window._hint_widget._title_label.text()
        )

    def test_refresh_clears_the_error(self, window):
        _Plugin.fail_on = "collect"
        try:
            window.refresh()
        finally:
            _Plugin.fail_on = None
        assert not window._placeholders_widget._error_widget.isHidden()

        window.refresh()

        assert window._placeholders_widget._error_widget.isHidden()
        assert not window._placeholders_widget._empty_widget.isHidden()


class TestCompletionsErrors:
    def test_completion_error_is_shown_in_preview(self, window):
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})
        editor = window._editor_widget

        _Plugin.fail_on = "completions"
        try:
            editor._on_dynamic_timer()
        finally:
            _Plugin.fail_on = None

        assert "completions boom" in (
            editor._preview_widget._hint_label.text()
        )


class TestRunSupport:
    def test_run_all_uses_populate_fallback(self, qtbot, monkeypatch):
        monkeypatch.setattr(
            _Plugin,
            "repopulate_placeholder",
            PlaceholderPlugin.repopulate_placeholder,
        )
        controller = WorkfileTemplateBuilderController(_Builder(None))
        window = WorkfileTemplateBuilderWindow(controller)
        qtbot.addWidget(window)
        window.show()
        qtbot.waitExposed(window)

        window._on_create_request("fake")
        window._on_create_confirmed("fake", {"name": "one"})

        test_build_btn = window._context_bar._test_build_btn
        assert test_build_btn.isEnabled()

        result = window._controller.run_template_build()
        window._update_build_status(result)

        assert "1 populated" in window._build_status_btn.text()


class TestUnsavedChangeGuards:
    def _create_placeholder(self, window):
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})
        assert window._pages_widget.currentIndex() == EDITOR_PAGE
        assert window._current_identifier == "node_1"

    def test_close_asks_for_dirty_changes(self, window, answers):
        self._create_placeholder(window)
        _name_input(window).setText("changed")

        answers.queue.append(QtWidgets.QMessageBox.Cancel)
        window.close()
        assert window.isVisible()

        answers.queue.append(QtWidgets.QMessageBox.Discard)
        window.close()
        assert window.isHidden()

    def test_create_mode_switch_asks_to_discard(self, window, answers):
        self._create_placeholder(window)
        window._on_create_request()
        _name_input(window).setText("changed")

        answers.queue.append(QtWidgets.QMessageBox.Cancel)
        window._placeholders_widget.select_identifier("node_1")
        assert window._editor_widget.is_create_mode()

        answers.queue.append(QtWidgets.QMessageBox.Discard)
        window._placeholders_widget.select_identifier("node_1")
        assert not window._editor_widget.is_create_mode()
        assert window._current_identifier == "node_1"

    def test_create_mode_cancel_asks_to_discard(self, window, answers):
        window._on_create_request()
        _name_input(window).setText("changed")

        answers.queue.append(QtWidgets.QMessageBox.Cancel)
        window._on_create_cancelled()
        assert window._pages_widget.currentIndex() == EDITOR_PAGE

        answers.queue.append(QtWidgets.QMessageBox.Discard)
        window._on_create_cancelled()
        assert window._pages_widget.currentIndex() == HINT_PAGE

    def test_filter_does_not_close_editor_or_ask(self, window, answers):
        self._create_placeholder(window)
        _name_input(window).setText("changed")
        answers.queue.append(QtWidgets.QMessageBox.Cancel)

        filter_input = window._placeholders_widget._filter_input
        filter_input.setText("zzz")

        assert answers.queue
        assert window._pages_widget.currentIndex() == EDITOR_PAGE
        assert window._current_identifier == "node_1"
        assert window._editor_widget.has_unsaved_changes()

        filter_input.setText("")
        assert window._pages_widget.currentIndex() == EDITOR_PAGE
        assert (
            window._placeholders_widget.get_selected_identifier()
            == "node_1"
        )

    def test_empty_list_click_keeps_editor(self, window, answers):
        self._create_placeholder(window)
        _name_input(window).setText("changed")
        answers.queue.append(QtWidgets.QMessageBox.Cancel)

        window._placeholders_widget._view.selectionModel().clearSelection()

        assert answers.queue
        assert window._pages_widget.currentIndex() == EDITOR_PAGE
        assert window._editor_widget.has_unsaved_changes()

    def test_discard_on_refresh_reverts_editor(self, window, answers):
        self._create_placeholder(window)
        _name_input(window).setText("changed")

        answers.queue.append(QtWidgets.QMessageBox.Discard)
        window._on_refresh_request()

        assert _name_input(window).text() == "one"
        assert not window._editor_widget.has_unsaved_changes()
        assert window._pages_widget.currentIndex() == EDITOR_PAGE

    def test_refresh_updates_editor_from_scene(self, window, builder):
        self._create_placeholder(window)
        builder.nodes["node_1"]["name"] = "changed outside"

        window.refresh()

        assert _name_input(window).text() == "changed outside"
        assert not window._editor_widget.has_unsaved_changes()

    def test_removed_placeholder_shows_notice(self, window, builder):
        self._create_placeholder(window)
        builder.nodes.pop("node_1")

        window.refresh()

        assert window._pages_widget.currentIndex() == HINT_PAGE
        assert (
            window._hint_widget._title_label.text()
            == "Placeholder no longer exists"
        )

    def test_removed_placeholder_keeps_dirty_form(self, window, builder):
        self._create_placeholder(window)
        _name_input(window).setText("changed")
        builder.nodes.pop("node_1")

        window.refresh()

        assert window._pages_widget.currentIndex() == EDITOR_PAGE
        assert _name_input(window).text() == "changed"
        assert window._editor_widget.has_unsaved_changes()

    def test_long_context_is_elided(self, window):
        window._context_bar.set_build_context(
            BuildContextItem("/short/folder", "modeling", False)
        )
        window.layout().activate()
        short_width = window.minimumSizeHint().width()

        long_folder = "/assets/" + "/".join(
            ["very_long_asset_folder_name"] * 8
        )
        label = "{} \u00b7 animation".format(long_folder)
        window._context_bar.set_build_context(
            BuildContextItem(long_folder, "animation", True)
        )
        window.layout().activate()

        button = window._context_bar._context_btn
        assert window.minimumSizeHint().width() <= short_width + 100
        assert label in button.toolTip()
        assert button.text() != label
        window._context_bar.layout().activate()
        assert (
            window._context_bar._test_build_btn.geometry().right()
            <= window._context_bar.width()
        )


class TestRenamedPlaceholder:
    def test_save_keeps_renamed_placeholder_selected(
        self, window, monkeypatch
    ):
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})

        def rename_update(plugin, placeholder_item, placeholder_data):
            plugin.nodes.pop(placeholder_item.scene_identifier)
            plugin.nodes["renamed"] = dict(placeholder_data)

        monkeypatch.setattr(_Plugin, "update_placeholder", rename_update)

        window._on_save_confirmed("node_1", {"name": "renamed"})

        assert window._current_identifier == "renamed"
        assert window._editor_widget.get_scene_identifier() == "renamed"
        assert (
            window._placeholders_widget.get_selected_identifier()
            == "renamed"
        )

    def test_host_event_refreshes_window(self, window, builder):
        from ayon_core.lib import emit_event

        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})
        builder.nodes["node_1"]["name"] = "changed outside"

        emit_event("taskChanged", {})

        assert _name_input(window).text() == "changed outside"


class TestListReadability:
    def test_order_column_is_hidden(self, window):
        view = window._placeholders_widget._view
        assert view.isColumnHidden(ORDER_COLUMN)
        assert view.header().sectionSize(TYPE_COLUMN) == 150

    def test_splitter_starts_with_a_wide_list(self, window):
        splitter = window.findChild(QtWidgets.QSplitter)
        assert splitter.sizes()[0] >= 400

    def test_pending_row_is_readable(self, window):
        window._on_create_request()
        labels = _list_labels(window)
        assert "New placeholder" in labels


class TestPreviewCopy:
    def test_preview_rows_are_selectable_and_copyable(self, window):
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})
        editor = window._editor_widget
        editor._on_dynamic_timer()

        preview = editor._preview_widget
        assert (
            preview._items_view.selectionMode()
            == QtWidgets.QAbstractItemView.ExtendedSelection
        )
        preview._items_view.selectionModel().select(
            preview._items_model.index(0, 0),
            QtCore.QItemSelectionModel.ClearAndSelect
            | QtCore.QItemSelectionModel.Rows,
        )
        preview._copy_selected()
        clipboard = QtWidgets.QApplication.clipboard().text()
        assert "/assets/bob" in clipboard
        assert "v001 - ma" in clipboard

        detail_item = preview._items_model.item(0, 1)
        assert detail_item.toolTip() == "v001 - ma"

        preview._copy_all()
        assert QtWidgets.QApplication.clipboard().text() == (
            "/assets/bob - v001 - ma"
        )


class TestKeyboardShortcuts:
    def test_save_shortcut_saves_changes(self, window, builder):
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})
        _name_input(window).setText("changed")

        window._on_save_shortcut()

        assert builder.nodes["node_1"]["name"] == "changed"

    def test_escape_reverts_dirty_editor(self, window):
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})
        _name_input(window).setText("changed")

        window._on_escape()

        assert _name_input(window).text() == "one"
        assert window._pages_widget.currentIndex() == EDITOR_PAGE
        assert not window._editor_widget.has_unsaved_changes()

    def test_escape_closes_clean_window(self, window):
        window._on_escape()

        assert window.isHidden()


class TestBusyState:
    def test_run_all_marks_the_window_busy(self, window, answers, monkeypatch):
        seen = []

        def fake_run(progress_callback=None):
            seen.append(
                (window._busy, window._context_bar.isEnabled())
            )
            progress_callback(1, {})
            return ActionResult(success=True)

        monkeypatch.setattr(
            window._controller, "run_template_build", fake_run
        )
        answers.queue.append(QtWidgets.QMessageBox.Yes)

        window._on_run_template_build_request()

        assert seen == [(True, False)]
        assert not window._busy
        assert window._context_bar.isEnabled()

    def test_run_one_marks_the_window_busy(
        self, window, monkeypatch
    ):
        seen = []

        def fake_run(scene_identifier):
            seen.append(window._busy)
            return ActionResult(success=True)

        monkeypatch.setattr(
            window._controller, "run_placeholder", fake_run
        )
        window._on_create_request()
        window._on_create_confirmed("fake", {"name": "one"})

        window._on_run_request("node_1")

        assert seen == [True]
        assert not window._busy


class TestWindowSingleton:
    @pytest.fixture(autouse=True)
    def _reset_window_ref(self):
        from ayon_core.tools.workfile_template_build import lib

        lib._WINDOW_REF = None
        yield
        lib._WINDOW_REF = None

    def test_window_is_reused(self, builder):
        from ayon_core.tools.workfile_template_build import (
            show_workfile_template_builder,
        )

        first = show_workfile_template_builder(builder)
        second = show_workfile_template_builder(builder)

        assert first is second
        assert first.testAttribute(QtCore.Qt.WA_DeleteOnClose)
        first.close()


class TestErrorBoundary:
    def test_update_failure_is_reported(self, window, monkeypatch):
        errors = []
        monkeypatch.setattr(
            window,
            "_show_unexpected_error",
            lambda title: errors.append(title),
        )
        monkeypatch.setattr(
            window._controller,
            "get_placeholder_plugin_items",
            lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        )

        window._update_placeholders()

        assert errors == ["Failed to update placeholders"]
