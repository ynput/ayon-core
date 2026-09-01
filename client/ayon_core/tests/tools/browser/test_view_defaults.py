from unittest.mock import Mock

from ayon_core.tools.browser.view_defaults import BROWSER_VIEW_DEFAULTS
from ayon_core.ui.components.views import ViewBindings, ViewSettings


def test_browser_view_defaults_create_complete_independent_settings():
    defaults = BROWSER_VIEW_DEFAULTS
    settings = defaults.create_settings(["productType", "productBaseType"])

    assert settings.sort_by == defaults.sort_by
    assert settings.sort_desc == defaults.sort_desc
    assert settings.row_height == defaults.row_height
    assert settings.grouping.group_by is None
    assert (
        settings.grouping.show_empty_groups
        == defaults.show_empty_groups
    )
    assert settings.filter.conditions[0]["values"] == ["Latest"]
    assert settings.extra == {
        "gridHeight": defaults.card_width,
        "displayType": defaults.display_type,
        "featuredVersionOrder": list(defaults.featured_version_order),
        "latestPerFolder": defaults.latest_per_folder,
        "includeChildren": defaults.include_children,
    }
    assert [
        state.name for state in settings.columns if state.visible
    ] == ["productType"]

    settings.extra["featuredVersionOrder"].reverse()
    fresh_settings = defaults.create_settings([])
    assert fresh_settings.extra["featuredVersionOrder"] == [
        "latestDone",
        "latest",
        "hero",
    ]


def test_view_bindings_apply_complete_default_settings():
    model = Mock()
    table_view = Mock()
    applied_extras = []
    defaults = BROWSER_VIEW_DEFAULTS.create_settings(["productType"])
    bindings = ViewBindings(
        model=model,
        table_view=table_view,
        default_settings=lambda: defaults,
        on_extra_apply=applied_extras.append,
    )

    bindings.apply(ViewSettings())

    applied_settings = model.apply_settings.call_args.args[0]
    assert applied_settings.sort_by == defaults.sort_by
    assert applied_settings.columns == defaults.columns
    table_view.set_row_height.assert_called_once_with(defaults.row_height)
    assert applied_extras == [defaults.extra]
