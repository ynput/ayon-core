from pydantic import validator

from ayon_server.settings import (
    BaseSettingsModel,
    SettingsField,
    task_types_enum,
    ensure_unique_names
)


class ValidatePluginModel(BaseSettingsModel):
    _isGroup = True
    enabled: bool = True
    optional: bool = SettingsField(True, title="Optional")
    active: bool = SettingsField(True, title="Active")


class ValidateFrameRangeModel(ValidatePluginModel):
    """Allows to publish multiple video files in one go. <br />Name of matching
     asset is parsed from file names ('asset.mov', 'asset_v001.mov',
     'my_asset_to_publish.mov')"""


class ExtractEditorialPckgFFmpegModel(BaseSettingsModel):
    video_filters: list[str] = SettingsField(
        default_factory=list,
        title="Video filters"
    )
    audio_filters: list[str] = SettingsField(
        default_factory=list,
        title="Audio filters"
    )
    input: list[str] = SettingsField(
        default_factory=list,
        title="Input arguments"
    )
    output: list[str] = SettingsField(
        default_factory=list,
        title="Output arguments"
    )


class ExtractEditorialPckgOutputDefModel(BaseSettingsModel):
    """Set extension and ffmpeg arguments. See `ExtractReview` for example."""
    _layout = "expanded"
    name: str = SettingsField("", title="Name")
    ext: str = SettingsField("", title="Output extension")

    ffmpeg_args: ExtractEditorialPckgFFmpegModel = SettingsField(
        default_factory=ExtractEditorialPckgFFmpegModel,
        title="FFmpeg arguments"
    )


class ExtractEditorialPckgProfileModel(BaseSettingsModel):
    product_types: list[str] = SettingsField(
        default_factory=list,
        title="Product types"
    )
    task_types: list[str] = SettingsField(
        default_factory=list,
        title="Task types",
        enum_resolver=task_types_enum
    )
    task_names: list[str] = SettingsField(
        default_factory=list,
        title="Task names"
    )
    product_names: list[str] = SettingsField(
        default_factory=list,
        title="Product names"
    )
    outputs: list[ExtractEditorialPckgOutputDefModel] = SettingsField(
        default_factory=list,
        title="Output Definitions",
    )

    @validator("outputs")
    def validate_unique_outputs(cls, value):
        ensure_unique_names(value)
        return value


class ExtractEditorialPckgConversionModel(BaseSettingsModel):
    """Conversion of input movie files into expected format."""
    enabled: bool = SettingsField(True)
    profiles: list[ExtractEditorialPckgProfileModel] = SettingsField(
        default_factory=list, title="Profiles"
    )


class TrayPublisherPublishPlugins(BaseSettingsModel):
    CollectFrameDataFromAssetEntity: ValidatePluginModel = SettingsField(
        default_factory=ValidatePluginModel,
        title="Collect Frame Data From Folder Entity",
    )
    ValidateFrameRange: ValidateFrameRangeModel = SettingsField(
        title="Validate Frame Range",
        default_factory=ValidateFrameRangeModel,
    )
    ValidateExistingVersion: ValidatePluginModel = SettingsField(
        title="Validate Existing Version",
        default_factory=ValidatePluginModel,
    )

    ExtractEditorialPckgConversion: ExtractEditorialPckgConversionModel = (
        SettingsField(
            default_factory=ExtractEditorialPckgConversionModel,
            title="Extract Editorial Package Conversion"
        )
    )


DEFAULT_PUBLISH_PLUGINS = {
    "CollectFrameDataFromAssetEntity": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ValidateFrameRange": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ValidateExistingVersion": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ExtractEditorialPckgConversion": {
        "enabled": True,
        "optional": True,
        "active": True
    }
}
