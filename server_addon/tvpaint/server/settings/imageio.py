from pydantic import validator
from ayon_server.settings import BaseSettingsModel, SettingsField
from ayon_server.settings.validators import ensure_unique_names


class ImageIOConfigModel(BaseSettingsModel):
    """[DEPRECATED] Addon OCIO config settings. Please set the OCIO config
    path in the Core addon profiles here
    (ayon+settings://core/imageio/ocio_config_profiles).
    """

    override_global_config: bool = SettingsField(
        False,
        title="Override global OCIO config",
        description=(
            "DEPRECATED functionality. Please set the OCIO config path in the "
            "Core addon profiles here (ayon+settings://core/imageio/"
            "ocio_config_profiles)."
        ),
    )
    filepath: list[str] = SettingsField(
        default_factory=list,
        title="Config path",
        description=(
            "DEPRECATED functionality. Please set the OCIO config path in the "
            "Core addon profiles here (ayon+settings://core/imageio/"
            "ocio_config_profiles)."
        ),
    )


class ImageIOFileRuleModel(BaseSettingsModel):
    name: str = SettingsField("", title="Rule name")
    pattern: str = SettingsField("", title="Regex pattern")
    colorspace: str = SettingsField("", title="Colorspace name")
    ext: str = SettingsField("", title="File extension")


class ImageIOFileRulesModel(BaseSettingsModel):
    activate_host_rules: bool = SettingsField(False)
    rules: list[ImageIOFileRuleModel] = SettingsField(
        default_factory=list,
        title="Rules"
    )

    @validator("rules")
    def validate_unique_outputs(cls, value):
        ensure_unique_names(value)
        return value


class TVPaintImageIOModel(BaseSettingsModel):
    activate_host_color_management: bool = SettingsField(
        True, title="Enable Color Management"
    )
    ocio_config: ImageIOConfigModel = SettingsField(
        default_factory=ImageIOConfigModel,
        title="OCIO config"
    )
    file_rules: ImageIOFileRulesModel = SettingsField(
        default_factory=ImageIOFileRulesModel,
        title="File Rules"
    )
