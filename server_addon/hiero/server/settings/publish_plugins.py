from pydantic import validator
from ayon_server.settings import (
    BaseSettingsModel,
    SettingsField,
    ensure_unique_names,
    normalize_name,
)


class CollectClipEffectsDefModel(BaseSettingsModel):
    _layout = "expanded"
    name: str = SettingsField("", title="Name")
    effect_classes: list[str] = SettingsField(
        default_factory=list, title="Effect Classes"
    )

    @validator("name")
    def validate_name(cls, value):
        """Ensure name does not contain weird characters"""
        return normalize_name(value)


class CollectClipEffectsTracksModel(BaseSettingsModel):
    _layout = "expanded"
    name: str = SettingsField("", title="Name")
    track_names: list[str] = SettingsField("", title="Track Names")


class CollectClipEffectsModel(BaseSettingsModel):
    effect_categories: list[CollectClipEffectsDefModel] = SettingsField(
        default_factory=list, title="Effect Categories"
    )

    effect_tracks: list[CollectClipEffectsTracksModel] = SettingsField(
        default_factory=list, title="Effect Tracks"
    )

    @validator("effect_categories")
    def validate_unique_outputs(cls, value):
        ensure_unique_names(value)
        return value


class PublishPluginsModel(BaseSettingsModel):
    CollectClipEffects: CollectClipEffectsModel = SettingsField(
        default_factory=CollectClipEffectsModel,
        title="Collect Clip Effects"
    )


DEFAULT_PUBLISH_PLUGIN_SETTINGS = {
    "CollectClipEffectsModel": {
        "effect_categories": [],
        "effect_tracks": []
    }
}
