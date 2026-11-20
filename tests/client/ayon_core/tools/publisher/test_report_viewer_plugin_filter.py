"""Tests for plugin filtering in the publish report viewer 'Details' tab."""

from __future__ import annotations

import pytest
from qtpy import QtCore

from ayon_core.pipeline.publish.report import (
    CONTEXT_ID,
    PublishPluginReportInfo,
    PublishProcessReport,
    PublishReport,
)
from ayon_core.tools.publisher.publish_report_viewer import (
    PublishReportViewerWidget,
)
from ayon_core.tools.publisher.publish_report_viewer.constants import (
    ITEM_ID_ROLE,
    ITEM_IS_GROUP_ROLE,
    PLUGIN_PROCESS_TIME_ROLE,
    PLUGIN_PROCESS_TIME_RATIO_ROLE,
    PLUGIN_STATE_FAILED,
    PLUGIN_STATE_PENDING,
    PLUGIN_STATE_SKIPPED,
    PLUGIN_STATE_SUCCESSFUL,
)
from ayon_core.tools.publisher.publish_report_viewer.lib import (
    PROCESS_TIME_COLOR_STOPS,
    get_process_time_ratio,
    get_process_time_rgb,
    text_filter_matches,
)
from ayon_core.tools.publisher.publish_report_viewer.model import (
    PluginProxyModel,
    PluginsModel,
)


@pytest.mark.parametrize(
    ("filter_text", "values", "expected"),
    [
        ("", ["anything"], True),
        ("  ", ["anything"], True),
        ("render", ["Collect Render Layers"], True),
        ("RENDER", ["collect render layers"], True),
        ("nope", ["Collect Render Layers"], False),
        ("render", [None, "", "CollectRender"], True),
        # Wildcards match the whole value
        ("collect*", ["Collect Render Layers"], True),
        ("render*", ["Collect Render Layers"], False),
        ("*render*", ["Collect Render Layers"], True),
        ("*.py", ["/path/to/collect_render.py"], True),
        ("collect_?ender*", ["collect_render.py"], True),
        # '[' is literal, only '*' and '?' are wildcards
        ("[maya", ["Validate [Maya] Scene"], True),
        ("*[maya]*", ["Validate [Maya] Scene"], True),
        ("[cv]*", ["Validate Something"], False),
        # Any value can match
        ("*layers", ["CollectRender", "/p/x.py", "Render Layers"], True),
    ],
)
def test_text_filter_matches(filter_text, values, expected):
    assert text_filter_matches(filter_text, values) is expected


def _plugin(
    plugin_id: str,
    name: str,
    label: str,
    order: float,
    filepath: str,
    process_times: list[float] | None = None,
    skipped: bool = False,
    passed: bool | None = None,
) -> PublishPluginReportInfo:
    if passed is None:
        passed = not skipped
    return PublishPluginReportInfo(
        id=plugin_id,
        name=name,
        label=label,
        order=order,
        filepath=filepath,
        docstring=None,
        plugin_type="context",
        families=["*"],
        targets=["default"],
        skipped=skipped,
        passed=passed,
        process_reports=[
            PublishProcessReport(CONTEXT_ID, [], process_time)
            for process_time in process_times or []
        ],
    )


@pytest.fixture
def report() -> PublishReport:
    return PublishReport(
        label="test",
        plugins_info=[
            _plugin(
                "p1", "CollectRender", "Collect Render Layers", 0.0,
                "/addons/maya/plugins/publish/collect_render.py",
                [100.0, 250.0],
            ),
            _plugin(
                "p2", "CollectScene", "Collect Scene", 0.1,
                "/addons/core/plugins/publish/collect_scene.py",
                [5.0],
            ),
            _plugin(
                "p3", "ValidateFrameRange", "Validate Frame Range", 1.0,
                "/addons/core/plugins/publish/validate_frame_range.py",
                skipped=True,
            ),
            _plugin(
                "p6", "ValidateBroken", "Validate Broken", 1.1,
                "/addons/core/plugins/publish/validate_broken.py",
                [20.0],
            ),
            _plugin(
                "p4", "ExtractReview", "Extract Review", 2.0,
                "/addons/core/plugins/publish/extract_review.py",
                [1500.0],
            ),
            _plugin(
                "p5", "IntegrateAsset", "Integrate Asset", 3.0,
                "/addons/core/plugins/publish/integrate.py",
                passed=False,
            ),
        ],
    )


def _visible(proxy: PluginProxyModel) -> tuple[list[str], list[str]]:
    groups = []
    plugin_ids = []
    for group_row in range(proxy.rowCount()):
        group_index = proxy.index(group_row, 0)
        assert group_index.data(ITEM_IS_GROUP_ROLE)
        groups.append(group_index.data(QtCore.Qt.DisplayRole))
        for row in range(proxy.rowCount(group_index)):
            plugin_ids.append(
                proxy.index(row, 0, group_index).data(ITEM_ID_ROLE)
            )
    return groups, plugin_ids


@pytest.fixture
def proxy(report) -> PluginProxyModel:
    model = PluginsModel()
    model.set_report(report, {"p6"})
    proxy = PluginProxyModel()
    proxy.setSourceModel(model)
    proxy._model = model  # keep source model alive
    return proxy


def test_proxy_default_states_and_empty_groups(proxy):
    # Pending, successful and failed shown, skipped hidden
    groups, plugin_ids = _visible(proxy)
    assert plugin_ids == ["p1", "p2", "p6", "p4", "p5"]
    assert groups == ["Collect", "Validate", "Extract", "Integrate"]


@pytest.mark.parametrize(
    ("states", "expected"),
    [
        ({PLUGIN_STATE_SKIPPED}, ["p3"]),
        ({PLUGIN_STATE_PENDING}, ["p5"]),
        ({PLUGIN_STATE_SUCCESSFUL}, ["p1", "p2", "p4"]),
        ({PLUGIN_STATE_FAILED}, ["p6"]),
        (set(), []),
        (
            {
                PLUGIN_STATE_SKIPPED, PLUGIN_STATE_PENDING,
                PLUGIN_STATE_SUCCESSFUL, PLUGIN_STATE_FAILED,
            },
            ["p1", "p2", "p3", "p6", "p4", "p5"],
        ),
    ],
)
def test_proxy_state_filter(proxy, states, expected):
    for state in (
        PLUGIN_STATE_SKIPPED, PLUGIN_STATE_PENDING,
        PLUGIN_STATE_SUCCESSFUL, PLUGIN_STATE_FAILED,
    ):
        proxy.set_state_visible(state, state in states)
    _, plugin_ids = _visible(proxy)
    assert plugin_ids == expected


@pytest.mark.parametrize(
    ("filter_text", "expected"),
    [
        ("render", ["p1"]),  # label, name and filepath
        ("CollectScene", ["p2"]),  # class name
        ("maya", ["p1"]),  # directory in filepath
        ("collect*", ["p1", "p2"]),  # label/name start
        ("*review.py", ["p4"]),  # filepath end
        ("frame", []),  # skipped plugin stays hidden
    ],
)
def test_proxy_text_filter(proxy, filter_text, expected):
    proxy.set_filter_text(filter_text)
    _, plugin_ids = _visible(proxy)
    assert plugin_ids == expected


def test_proxy_text_filter_with_skipped_shown(proxy):
    proxy.set_state_visible(PLUGIN_STATE_SKIPPED, True)
    proxy.set_filter_text("frame")
    groups, plugin_ids = _visible(proxy)
    assert plugin_ids == ["p3"]
    assert groups == ["Validate"]


def test_model_process_time(proxy):
    model = proxy._model
    times = {}
    ratios = {}
    for group_row in range(model.rowCount()):
        group_index = model.index(group_row, 0)
        for row in range(model.rowCount(group_index)):
            index = model.index(row, 0, group_index)
            plugin_id = index.data(ITEM_ID_ROLE)
            times[plugin_id] = index.data(PLUGIN_PROCESS_TIME_ROLE)
            ratios[plugin_id] = index.data(PLUGIN_PROCESS_TIME_RATIO_ROLE)
    assert times == {
        "p1": 350.0, "p2": 5.0, "p3": None,
        "p4": 1500.0, "p5": None, "p6": 20.0,
    }
    # Relative to slowest plugin
    assert ratios == pytest.approx({
        "p1": 350 / 1500, "p2": 5 / 1500, "p3": 0.0,
        "p4": 1.0, "p5": 0.0, "p6": 20 / 1500,
    })


def _apply_filter(widget: PublishReportViewerWidget, text: str) -> None:
    widget._plugins_filter_input.setText(text)
    widget._plugins_filter_timer.stop()
    widget._on_plugins_filter_timer()


def _select_plugin(widget: PublishReportViewerWidget, plugin_id: str):
    view = widget._plugins_view
    proxy = widget._plugins_proxy
    for group_row in range(proxy.rowCount()):
        group_index = proxy.index(group_row, 0)
        for row in range(proxy.rowCount(group_index)):
            index = proxy.index(row, 0, group_index)
            if index.data(ITEM_ID_ROLE) == plugin_id:
                view.selectionModel().select(
                    index, QtCore.QItemSelectionModel.ClearAndSelect
                )
                return
    raise AssertionError(f"Plugin '{plugin_id}' not visible")


def test_widget_scopes_details_by_filter(qtbot, report):
    widget = PublishReportViewerWidget()
    qtbot.addWidget(widget)
    widget.set_report(report)

    logs_widget = widget._logs_text_widget
    details_widget = widget._plugins_details_widget

    # No filter, no selection -> all logs
    assert logs_widget._plugin_filter is None
    assert details_widget._plugin_filter == set()

    # Filter, no selection -> visible plugins only
    _apply_filter(widget, "collect")
    assert logs_widget._plugin_filter == {"p1", "p2"}
    assert details_widget._plugin_filter == {"p1", "p2"}

    # Selection wins over filter
    _select_plugin(widget, "p2")
    assert logs_widget._plugin_filter == {"p2"}
    assert details_widget._plugin_filter == {"p2"}

    # Filter hiding selected plugin drops it from selection
    _apply_filter(widget, "render")
    assert logs_widget._plugin_filter == {"p1"}

    # No matches -> no logs
    _apply_filter(widget, "does-not-exist")
    assert logs_widget._plugin_filter == set()
    assert details_widget._plugin_filter == set()

    # Clearing filter -> all logs again
    _apply_filter(widget, "")
    assert logs_widget._plugin_filter is None

    # Hidden state without text filter -> visible plugins only
    widget._state_actions_by_state[PLUGIN_STATE_SUCCESSFUL].setChecked(False)
    assert logs_widget._plugin_filter == {"p5"}
    assert details_widget._plugin_filter == {"p5"}

    # Showing skipped plugins alone does not count as filter
    widget._state_actions_by_state[PLUGIN_STATE_SUCCESSFUL].setChecked(True)
    widget._state_actions_by_state[PLUGIN_STATE_SKIPPED].setChecked(True)
    assert logs_widget._plugin_filter is None


def test_widget_keeps_filter_on_new_report(qtbot, report):
    widget = PublishReportViewerWidget()
    qtbot.addWidget(widget)
    widget.set_report(report)
    _apply_filter(widget, "extract")

    widget.set_report(report)
    assert widget._logs_text_widget._plugin_filter == {"p4"}


def test_widget_filter_controls(qtbot, report):
    widget = PublishReportViewerWidget()
    qtbot.addWidget(widget)
    widget.set_report(report)

    # Clear action is visible only with text and clears the filter
    clear_action = widget._plugins_filter_input._clear_action
    assert not clear_action.isVisible()
    widget._plugins_filter_input.setText("collect")
    assert clear_action.isVisible()
    clear_action.trigger()
    assert widget._plugins_filter_input.text() == ""
    assert not clear_action.isVisible()

    # State toggles in settings menu
    state_actions = widget._state_actions_by_state
    assert {
        state for state, action in state_actions.items()
        if action.isChecked()
    } == {
        PLUGIN_STATE_PENDING, PLUGIN_STATE_SUCCESSFUL, PLUGIN_STATE_FAILED
    }
    state_actions[PLUGIN_STATE_SKIPPED].setChecked(True)
    assert widget._plugins_proxy.is_state_visible(PLUGIN_STATE_SKIPPED)
    state_actions[PLUGIN_STATE_FAILED].setChecked(False)
    assert not widget._plugins_proxy.is_state_visible(PLUGIN_STATE_FAILED)

    # Time bars option
    assert not widget._plugins_delegate._show_time_bars
    widget._show_time_bars_action.setChecked(True)
    assert widget._plugins_delegate._show_time_bars

    # Show plugin times setting, hidden by default
    delegate = widget._plugins_delegate
    assert not widget._show_plugin_times_action.isChecked()
    assert not delegate._show_process_time
    widget._show_plugin_times_action.setChecked(True)
    assert delegate._show_process_time


@pytest.mark.parametrize(
    ("process_time", "expected"),
    [
        (0.0, 0.0),
        (10.0, 0.0),
        (100.0, 1 / 3),
        (1000.0, 2 / 3),
        (10000.0, 1.0),
        (99999.0, 1.0),
    ],
)
def test_process_time_ratio(process_time, expected):
    assert get_process_time_ratio(process_time) == pytest.approx(expected)


def test_process_time_rgb():
    def hex_rgb(value):
        value = value.lstrip("#")
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))

    stops = PROCESS_TIME_COLOR_STOPS
    assert get_process_time_rgb(1.0) == hex_rgb(stops[0][1])
    assert get_process_time_rgb(60000.0) == hex_rgb(stops[-1][1])
    # Inner stops are hit exactly (ratio 0.6 is 10 ** 2.8 ms ~ 631ms)
    for pos, color in stops[1:-1]:
        process_time = 10 ** (1 + pos * 3)
        assert get_process_time_rgb(process_time) == hex_rgb(color)


def test_settings_menu_stays_open_on_toggle(qtbot, report):
    widget = PublishReportViewerWidget()
    qtbot.addWidget(widget)
    widget.set_report(report)
    widget.show()

    menu = widget._plugins_settings_menu
    menu.popup(QtCore.QPoint(0, 0))
    qtbot.waitExposed(menu)
    action = widget._state_actions_by_state[PLUGIN_STATE_SKIPPED]
    assert not action.isChecked()

    pos = menu.actionGeometry(action).center()
    qtbot.mouseMove(menu, pos)
    menu.setActiveAction(action)
    qtbot.mouseClick(menu, QtCore.Qt.LeftButton, pos=pos)
    assert action.isChecked()
    assert menu.isVisible()
    assert widget._plugins_proxy.is_state_visible(PLUGIN_STATE_SKIPPED)
    menu.close()


def test_group_process_time_sums_ran_plugins(proxy):
    model = proxy._model
    totals = {
        model.index(row, 0).data(QtCore.Qt.DisplayRole): (
            model.index(row, 0).data(PLUGIN_PROCESS_TIME_ROLE)
        )
        for row in range(model.rowCount())
    }
    assert totals == {
        "Collect": 355.0, "Validate": 20.0, "Extract": 1500.0,
        # Only pending plugin without process time
        "Integrate": None,
    }


def test_proxy_ignore_skipped_api(proxy):
    assert proxy.ignore_skipped
    proxy.set_ignore_skipped(False)
    assert proxy.is_state_visible(PLUGIN_STATE_SKIPPED)
    assert not proxy.ignore_skipped
    _, plugin_ids = _visible(proxy)
    assert "p3" in plugin_ids


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (-1.0, "0.00ms"),
        (0.0, "0.00ms"),
        (0.42, "0.42ms"),
        (0.996, "1.0ms"),
        (4.2, "4.2ms"),
        (9.96, "10ms"),
        (42.4, "42ms"),
        (420.0, "420ms"),
        (999.4, "999ms"),
        (999.6, "1.00s"),
        (4200.0, "4.20s"),
        (9996.0, "10.0s"),
        (42000.0, "42.0s"),
        (59960.0, "1m 00s"),
        (90000.0, "1m 30s"),
        (245000.0, "4m 05s"),
        (3599600.0, "1h 00m"),
        (3840000.0, "1h 04m"),
        (9000000.0, "2h 30m"),
    ],
)
def test_get_pretty_milliseconds(value, expected):
    from ayon_core.tools.publisher.publish_report_viewer.lib import (
        get_pretty_milliseconds,
    )

    assert get_pretty_milliseconds(value) == expected
