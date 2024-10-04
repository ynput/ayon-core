import json
from pydantic import validator
from ayon_server.settings import (
    BaseSettingsModel,
    SettingsField,
    MultiplatformPathListModel,
    ensure_unique_names,
    task_types_enum,
)
from ayon_server.exceptions import BadRequestException

from .publish_plugins import PublishPuginsModel, DEFAULT_PUBLISH_VALUES
from .tools import GlobalToolsModel, DEFAULT_TOOLS_VALUES


class DiskMappingItemModel(BaseSettingsModel):
    _layout = "expanded"
    source: str = SettingsField("", title="Source")
    destination: str = SettingsField("", title="Destination")


class DiskMappingModel(BaseSettingsModel):
    windows: list[DiskMappingItemModel] = SettingsField(
        title="Windows",
        default_factory=list,
    )
    linux: list[DiskMappingItemModel] = SettingsField(
        title="Linux",
        default_factory=list,
    )
    darwin: list[DiskMappingItemModel] = SettingsField(
        title="MacOS",
        default_factory=list,
    )


class ImageIOFileRuleModel(BaseSettingsModel):
    name: str = SettingsField("", title="Rule name")
    pattern: str = SettingsField("", title="Regex pattern")
    colorspace: str = SettingsField("", title="Colorspace name")
    ext: str = SettingsField("", title="File extension")


class CoreImageIOFileRulesModel(BaseSettingsModel):
    activate_global_file_rules: bool = SettingsField(False)
    rules: list[ImageIOFileRuleModel] = SettingsField(
        default_factory=list,
        title="Rules"
    )

    @validator("rules")
    def validate_unique_outputs(cls, value):
        ensure_unique_names(value)
        return value


def _ocio_config_profile_types():
    return [
        {"value": "builtin_path", "label": "AYON built-in OCIO config"},
        {"value": "custom_path", "label": "Path to OCIO config"},
        {"value": "published_product", "label": "Published product"},
    ]


def _fallback_ocio_config_profile_types():
    return [
        {"value": "builtin_path", "label": "AYON built-in OCIO config"},
        {"value": "custom_path", "label": "Path to OCIO config"},
    ]


def _ocio_built_in_paths():
    return [
        {
            "value": "{BUILTIN_OCIO_ROOT}/aces_1.2/config.ocio",
            "label": "ACES 1.2",
            "description": "Aces 1.2 OCIO config file."
        },
        {
            "value": "{BUILTIN_OCIO_ROOT}/nuke-default/config.ocio",
            "label": "Nuke default",
        },
    ]


class FallbackProductModel(BaseSettingsModel):
    _layout = "expanded"
    fallback_type: str = SettingsField(
        title="Fallback config type",
        enum_resolver=_fallback_ocio_config_profile_types,
        conditionalEnum=True,
        default="builtin_path",
        description=(
            "Type of config which needs to be used in case published "
            "product is not found."
        ),
    )
    builtin_path: str = SettingsField(
        "ACES 1.2",
        title="Built-in OCIO config",
        enum_resolver=_ocio_built_in_paths,
        description=(
            "AYON ocio addon distributed OCIO config. "
            "Activated addon in bundle is required: 'ayon_ocio' >= 1.1.1"
        ),
    )
    custom_path: str = SettingsField(
        "",
        title="OCIO config path",
        description="Path to OCIO config. Anatomy formatting is supported.",
    )


class PublishedProductModel(BaseSettingsModel):
    _layout = "expanded"
    product_name: str = SettingsField(
        "",
        title="Product name",
        description=(
            "Context related published product name to get OCIO config from. "
            "Partial match is supported via use of regex expression."
        ),
    )
    fallback: FallbackProductModel = SettingsField(
        default_factory=FallbackProductModel,
    )


class CoreImageIOConfigProfilesModel(BaseSettingsModel):
    _layout = "expanded"
    host_names: list[str] = SettingsField(
        default_factory=list,
        title="Host names"
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
    type: str = SettingsField(
        title="Profile type",
        enum_resolver=_ocio_config_profile_types,
        conditionalEnum=True,
        default="builtin_path",
        section="---",
    )
    builtin_path: str = SettingsField(
        "ACES 1.2",
        title="Built-in OCIO config",
        enum_resolver=_ocio_built_in_paths,
        description=(
            "AYON ocio addon distributed OCIO config. "
            "Activated addon in bundle is required: 'ayon_ocio' >= 1.1.1"
        ),
    )
    custom_path: str = SettingsField(
        "",
        title="OCIO config path",
        description="Path to OCIO config. Anatomy formatting is supported.",
    )
    published_product: PublishedProductModel = SettingsField(
        default_factory=PublishedProductModel,
        title="Published product",
    )


class CoreImageIOBaseModel(BaseSettingsModel):
    activate_global_color_management: bool = SettingsField(
        False,
        title="Enable Color Management"
    )
    ocio_config_profiles: list[CoreImageIOConfigProfilesModel] = SettingsField(
        default_factory=list, title="OCIO config profiles"
    )
    file_rules: CoreImageIOFileRulesModel = SettingsField(
        default_factory=CoreImageIOFileRulesModel,
        title="File Rules"
    )


class VersionStartCategoryProfileModel(BaseSettingsModel):
    _layout = "expanded"
    host_names: list[str] = SettingsField(
        default_factory=list,
        title="Host names"
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
    product_types: list[str] = SettingsField(
        default_factory=list,
        title="Product types"
    )
    product_names: list[str] = SettingsField(
        default_factory=list,
        title="Product names"
    )
    version_start: int = SettingsField(
        1,
        title="Version Start",
        ge=0
    )


class VersionStartCategoryModel(BaseSettingsModel):
    profiles: list[VersionStartCategoryProfileModel] = SettingsField(
        default_factory=list,
        title="Profiles"
    )


class EnvironmentReplacementModel(BaseSettingsModel):
    environment_key: str = SettingsField("", title="Enviroment variable")
    pattern: str = SettingsField("", title="Pattern")
    replacement: str = SettingsField("", title="Replacement")


class FilterEnvsProfileModel(BaseSettingsModel):
    _layout = "expanded"

    host_names: list[str] = SettingsField(
        default_factory=list,
        title="Host names"
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

    folder_paths: list[str] = SettingsField(
        default_factory=list,
        title="Folder paths"
    )

    skip_env_keys: list[str] = SettingsField(
        default_factory=list,
        title="Skip environment variables"
    )
    replace_in_environment: list[EnvironmentReplacementModel] = SettingsField(
        default_factory=list,
        title="Replace values in environment"
    )


class CoreSettings(BaseSettingsModel):
    studio_name: str = SettingsField("", title="Studio name", scope=["studio"])
    studio_code: str = SettingsField("", title="Studio code", scope=["studio"])
    environments: str = SettingsField(
        "{}",
        title="Global environment variables",
        widget="textarea",
        scope=["studio"],
    )
    update_check_interval: int = SettingsField(
        5,
        title="Update check interval (minutes)",
        ge=0
    )
    disk_mapping: DiskMappingModel = SettingsField(
        default_factory=DiskMappingModel,
        title="Disk mapping",
    )
    tools: GlobalToolsModel = SettingsField(
        default_factory=GlobalToolsModel,
        title="Tools"
    )
    version_start_category: VersionStartCategoryModel = SettingsField(
        default_factory=VersionStartCategoryModel,
        title="Version start"
    )
    imageio: CoreImageIOBaseModel = SettingsField(
        default_factory=CoreImageIOBaseModel,
        title="Color Management (ImageIO)"
    )
    publish: PublishPuginsModel = SettingsField(
        default_factory=PublishPuginsModel,
        title="Publish plugins"
    )
    project_plugins: MultiplatformPathListModel = SettingsField(
        default_factory=MultiplatformPathListModel,
        title="Additional Project Plugin Paths",
    )
    project_folder_structure: str = SettingsField(
        "{}",
        widget="textarea",
        title="Project folder structure",
        description=(
            "Defines project folders to create on 'Create project folders'."
            "\n\n"
            "- In the launcher, this only creates the folders on disk and "
            " when the setting is empty it will be hidden from users in the"
            " launcher.\n"
            "- In `ayon-ftrack` this will create the folders on disk **and**"
            " will also create ftrack entities. It is never hidden there."
        ),
        section="---"
    )
    project_environments: str = SettingsField(
        "{}",
        widget="textarea",
        title="Project environments",
        section="---"
    )
    filter_env_profiles: list[FilterEnvsProfileModel] = SettingsField(
        default_factory=list,
    )

    @validator(
        "environments",
        "project_folder_structure",
        "project_environments")
    def validate_json(cls, value):
        if not value.strip():
            return "{}"
        try:
            converted_value = json.loads(value)
            success = isinstance(converted_value, dict)
        except json.JSONDecodeError:
            success = False

        if not success:
            raise BadRequestException(
                "Environment's can't be parsed as json object"
            )
        return value


DEFAULT_VALUES = {
    "imageio": {
        "activate_global_color_management": False,
        "ocio_config_profiles": [
            {
                "host_names": [],
                "task_types": [],
                "task_names": [],
                "type": "builtin_path",
                "builtin_path": "{BUILTIN_OCIO_ROOT}/aces_1.2/config.ocio",
                "custom_path": "",
                "published_product": {
                    "product_name": "",
                    "fallback": {
                        "fallback_type": "builtin_path",
                        "builtin_path": "ACES 1.2",
                        "custom_path": ""
                    }
                }
            }
        ],
        "file_rules": {
            "activate_global_file_rules": False,
            "rules": [
                {
                    "name": "example",
                    "pattern": ".*(beauty).*",
                    "colorspace": "ACES - ACEScg",
                    "ext": "exr",
                }
            ],
        },
    },
    "studio_name": "",
    "studio_code": "",
    "environments": json.dumps(
        {
            "STUDIO_SW": {
                "darwin": "/mnt/REPO_SW",
                "linux": "/mnt/REPO_SW",
                "windows": "P:/REPO_SW"
            }
        },
        indent=4
    ),
    "tools": DEFAULT_TOOLS_VALUES,
    "version_start_category": {
        "profiles": []
    },
    "publish": DEFAULT_PUBLISH_VALUES,
    "project_folder_structure": json.dumps(
        {
            "__project_root__": {
                "prod": {},
                "resources": {
                    "footage": {
                        "plates": {},
                        "offline": {}
                    },
                    "audio": {},
                    "art_dept": {}
                },
                "editorial": {},
                "assets": {
                    "characters": {},
                    "locations": {}
                },
                "shots": {}
            }
        },
        indent=4
    ),
    "project_plugins": {
        "windows": [],
        "darwin": [],
        "linux": []
    },
    "project_environments": json.dumps(
        {},
        indent=4
    ),
    "filter_env_profiles": [],
}
