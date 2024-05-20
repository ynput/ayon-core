from ayon_server.settings import (
    BaseSettingsModel,
    SettingsField,
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
    _layout = "expanded"
    ext: str = SettingsField("", title="Output extension")

    ffmpeg_args: ExtractEditorialPckgFFmpegModel = SettingsField(
        default_factory=ExtractEditorialPckgFFmpegModel,
        title="FFmpeg arguments"
    )


class ExtractEditorialPckgConversionModel(BaseSettingsModel):
    """Set output definition if resource files should be converted."""
    conversion_enabled: bool = SettingsField(True,
                                             title="Conversion enabled")
    output: ExtractEditorialPckgOutputDefModel = SettingsField(
        default_factory=ExtractEditorialPckgOutputDefModel,
        title="Output Definitions",
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
        "optional": False,
        "conversion_enabled": True,
        "output": {
            "ext": "",
            "ffmpeg_args": {
              "video_filters": [],
              "audio_filters": [],
              "input": [
                "-apply_trc gamma22"
              ],
              "output": [
                "-pix_fmt yuv420p",
                "-crf 18",
                "-intra"
              ]
            }
        }
    }
}
