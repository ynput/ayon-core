from pydantic import validator
from ayon_server.settings import BaseSettingsModel, SettingsField
from ayon_server.settings.validators import ensure_unique_names


class ImageIOConfigModel(BaseSettingsModel):
    override_global_config: bool = SettingsField(
        False,
        title="Override global OCIO config"
    )
    filepath: list[str] = SettingsField(
        default_factory=list,
        title="Config path"
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


class WorkfileImageIOModel(BaseSettingsModel):
    """Workfile settings help.

    Empty values will be skipped, allowing any existing env vars to
    pass through as defined.

    Note: The render space in Houdini is
    always set to the 'scene_linear' role."""

    enabled: bool = SettingsField(False, title="Enabled")
    default_display: str = SettingsField(
        title="Default active displays",
        description="It behaves like the 'OCIO_ACTIVE_DISPLAYS' env var,"
                    " Colon-separated list of displays, e.g ACES:P3"
    )
    default_view: str = SettingsField(
        title="Default active views",
        description="It behaves like the 'OCIO_ACTIVE_VIEWS' env var,"
                    " Colon-separated list of views, e.g sRGB:DCDM"
    )
    review_color_space: str = SettingsField(
        title="Review colorspace",
        description="It exposes OCIO Colorspace parameter in opengl nodes."
                    "if left empty, Ayon will figure out the default "
                    "colorspace using your default display and default view."
    )


class HoudiniImageIOModel(BaseSettingsModel):
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
    workfile: WorkfileImageIOModel = SettingsField(
        default_factory=WorkfileImageIOModel,
        title="Workfile"
    )


DEFAULT_IMAGEIO_SETTINGS = {
    "activate_host_color_management": False,
    "ocio_config": {
        "override_global_config": False,
        "filepath": []
    },
    "file_rules": {
        "activate_host_rules": False,
        "rules": []
    },
    "workfile": {
        "enabled": False,
        "default_display": "ACES",
        "default_view": "sRGB",
        "review_color_space": ""
    }
}
