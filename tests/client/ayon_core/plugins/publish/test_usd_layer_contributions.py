from ayon_core.plugins.publish.extract_usd_layer_contributions import (
    CollectUSDLayerContributions,
    LEGACY_VARIANT_IS_DEFAULT_KEY,
    VARIANT_DEFAULT_MODE_ALWAYS,
    VARIANT_DEFAULT_MODE_IF_NOT_SET,
    VARIANT_DEFAULT_MODE_KEY,
    VARIANT_DEFAULT_MODE_NEVER,
    _get_variant_default_mode,
    _should_set_variant_default,
    _variant_default_mode_from_value,
)


class _DummyInstance:
    def __init__(self, publish_attributes):
        self.publish_attributes = publish_attributes


def test_variant_default_mode_preserves_legacy_values():
    assert _variant_default_mode_from_value(True) == VARIANT_DEFAULT_MODE_ALWAYS
    assert (
        _variant_default_mode_from_value(False)
        == VARIANT_DEFAULT_MODE_IF_NOT_SET
    )
    assert (
        _variant_default_mode_from_value(None)
        == VARIANT_DEFAULT_MODE_IF_NOT_SET
    )


def test_variant_default_mode_accepts_new_values():
    assert (
        _variant_default_mode_from_value(VARIANT_DEFAULT_MODE_NEVER)
        == VARIANT_DEFAULT_MODE_NEVER
    )
    assert (
        _variant_default_mode_from_value(VARIANT_DEFAULT_MODE_IF_NOT_SET)
        == VARIANT_DEFAULT_MODE_IF_NOT_SET
    )
    assert (
        _variant_default_mode_from_value(VARIANT_DEFAULT_MODE_ALWAYS)
        == VARIANT_DEFAULT_MODE_ALWAYS
    )


def test_variant_default_mode_reads_new_key_before_legacy_key():
    assert _get_variant_default_mode({
        VARIANT_DEFAULT_MODE_KEY: VARIANT_DEFAULT_MODE_NEVER,
        LEGACY_VARIANT_IS_DEFAULT_KEY: True,
    }) == VARIANT_DEFAULT_MODE_NEVER


def test_variant_default_mode_falls_back_to_legacy_key():
    assert _get_variant_default_mode({
        LEGACY_VARIANT_IS_DEFAULT_KEY: True,
    }) == VARIANT_DEFAULT_MODE_ALWAYS
    assert _get_variant_default_mode({
        LEGACY_VARIANT_IS_DEFAULT_KEY: False,
    }) == VARIANT_DEFAULT_MODE_IF_NOT_SET


def test_convert_attribute_values_migrates_legacy_default_flag():
    instance = _DummyInstance({
        CollectUSDLayerContributions.__name__: {
            LEGACY_VARIANT_IS_DEFAULT_KEY: True,
        },
    })

    CollectUSDLayerContributions.convert_attribute_values(None, instance)

    plugin_values = instance.publish_attributes[
        CollectUSDLayerContributions.__name__
    ]
    assert plugin_values == {
        VARIANT_DEFAULT_MODE_KEY: VARIANT_DEFAULT_MODE_ALWAYS,
    }


def test_convert_attribute_values_keeps_new_default_mode():
    instance = _DummyInstance({
        CollectUSDLayerContributions.__name__: {
            VARIANT_DEFAULT_MODE_KEY: VARIANT_DEFAULT_MODE_NEVER,
            LEGACY_VARIANT_IS_DEFAULT_KEY: True,
        },
    })

    CollectUSDLayerContributions.convert_attribute_values(None, instance)

    plugin_values = instance.publish_attributes[
        CollectUSDLayerContributions.__name__
    ]
    assert plugin_values == {
        VARIANT_DEFAULT_MODE_KEY: VARIANT_DEFAULT_MODE_NEVER,
    }


def test_should_set_variant_default_only_when_requested():
    existing_selections = {"model": "main"}

    assert not _should_set_variant_default(
        VARIANT_DEFAULT_MODE_NEVER, "model", existing_selections
    )
    assert not _should_set_variant_default(
        VARIANT_DEFAULT_MODE_IF_NOT_SET, "model", existing_selections
    )
    assert _should_set_variant_default(
        VARIANT_DEFAULT_MODE_IF_NOT_SET, "look", existing_selections
    )
    assert _should_set_variant_default(
        VARIANT_DEFAULT_MODE_ALWAYS, "model", existing_selections
    )
