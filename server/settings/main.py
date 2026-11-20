import json
from pydantic import validator
from ayon_server.settings import (
    BaseSettingsModel,
    SettingsField,
    ensure_unique_names,
    task_types_enum,
)
from ayon_server.exceptions import BadRequestException

from .publish_plugins import PublishPuginsModel, DEFAULT_PUBLISH_VALUES
from .tools import GlobalToolsModel, DEFAULT_TOOLS_VALUES
from .workfile_actions import (
    WorkfileActionsModel,
    DEFAULT_WORKFILE_ACTIONS_VALUES,
)


class DiskMappingItemModel(BaseSettingsModel):
    _layout = "expanded"
    source: str = SettingsField(
        "",
        title="Source",
        description=(
            "Existing path (e.g. a network share) that should be made"
            " available under the destination path."
        ),
    )
    destination: str = SettingsField(
        "",
        title="Destination",
        description=(
            "Path under which the source will be accessible, e.g. a drive"
            " letter like `P:` on Windows or `/mnt/projects` on Linux."
        ),
    )


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
    name: str = SettingsField(
        "",
        title="Rule name",
        description="Unique name to identify the rule.",
    )
    pattern: str = SettingsField(
        "",
        title="Regex pattern",
        description=(
            "Regular expression searched for in the full file path, e.g."
            " `_plate_` or `.*/textures/.*`."
        ),
    )
    colorspace: str = SettingsField(
        "",
        title="Colorspace name",
        description=(
            "Colorspace to assign to matching files. Must exist in the"
            " active OCIO config, e.g. `ACEScg` or `sRGB - Texture`."
        ),
    )
    ext: str = SettingsField(
        "",
        title="File extension",
        description=(
            "Only apply the rule to files with this extension, e.g. `exr`."
            " Leave empty to match any extension."
        ),
    )


class CoreImageIOFileRulesModel(BaseSettingsModel):
    activate_global_file_rules: bool = SettingsField(
        False,
        title="Activate global file rules",
        description=(
            "Use the rules below for all hosts. A host that has its own"
            " file rules activated in its ImageIO settings uses those"
            " instead."
        ),
    )
    rules: list[ImageIOFileRuleModel] = SettingsField(
        default_factory=list,
        title="Rules",
        description=(
            "Rules to match files to a colorspace.\n\n"
            "A rule applies when a file matches both its extension and its"
            " regex pattern. If multiple rules match, the last one in the"
            " list wins."
        ),
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
        {"value": "disabled", "label": "Disable OCIO management"},
    ]


def _fallback_ocio_config_profile_types():
    return [
        {"value": "builtin_path", "label": "AYON built-in OCIO config"},
        {"value": "custom_path", "label": "Path to OCIO config"},
    ]


def _ocio_built_in_paths():
    return [
        {
            "value": "{BUILTIN_OCIO_ROOT}/aces_2.0/studio-config-v3.0.0_aces-v2.0_ocio-v2.4.ocio",  # noqa: E501
            "label": "ACES 2.0 Studio (OCIO v2.4)",
            "description": (
                "Aces 2.0 Studio OCIO config file. Requires OCIO v2.4.")
        },
        {
            "value": "{BUILTIN_OCIO_ROOT}/aces_1.3/studio-config-v1.0.0_aces-v1.3_ocio-v2.1.ocio",  # noqa: E501
            "label": "ACES 1.3 Studio (OCIO v2.1)",
            "description": (
                "Aces 1.3 Studio OCIO config file. Requires OCIO v2.1.")
        },
        {
            "value": "{BUILTIN_OCIO_ROOT}/aces_1.3/studio-config-v1.0.0_aces-v1.3_ocio-v2.0.ocio",  # noqa: E501
            "label": "ACES 1.3 Studio (OCIO v2)",
            "description": (
                "Aces 1.3 Studio OCIO config file. Requires OCIO v2.")
        },
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
        conditional_enum=True,
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


class ReviewLayersModel(BaseSettingsModel):
    review_layers: list[str] = SettingsField(
        default_factory=list,
        title="Review layers"
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
    app_names: list[str] = SettingsField(
        default_factory=list,
        title="Application names",
        placeholder="{group}/{variant} (maya/2026,  ...)",
        description=(
            "Application full name (group/variant) from applications addon."
        ),
    )
    type: str = SettingsField(
        title="Profile type",
        enum_resolver=_ocio_config_profile_types,
        conditional_enum=True,
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
        title="File Rules",
        description=(
            "Assign a colorspace to files by their path.\n\n"
            "For example, mark all `.exr` plates as `ACEScg`. Used when the"
            " colorspace of a published or loaded file is not otherwise"
            " known."
        ),
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
    product_base_types: list[str] = SettingsField(
        default_factory=list,
        title="Product base types"
    )
    product_names: list[str] = SettingsField(
        default_factory=list,
        title="Product names"
    )
    version_start: int = SettingsField(
        1,
        title="Version Start",
        ge=0,
        description=(
            "Version number of the first version of matching products and"
            " workfiles, e.g. `0` or `1`."
        ),
    )


class VersionStartCategoryModel(BaseSettingsModel):
    profiles: list[VersionStartCategoryProfileModel] = SettingsField(
        default_factory=list,
        title="Profiles",
        description=(
            "Version start per context.\n\n"
            "The first profile matching the host, task and product is used."
            " Empty filters match everything. Without a matching profile"
            " versions start at 1."
        ),
    )


class EnvironmentReplacementModel(BaseSettingsModel):
    environment_key: str = SettingsField(
        "",
        title="Environment variable",
        description="Name of the environment variable to modify.",
    )
    pattern: str = SettingsField(
        "",
        title="Pattern",
        description="Regular expression to search for in the value.",
    )
    replacement: str = SettingsField(
        "",
        title="Replacement",
        description=(
            "Text that replaces the matches. If the resulting value is"
            " empty, the variable is removed."
        ),
    )


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
        title="Skip environment variables",
        description=(
            "Environment variables to remove from the farm job environment."
        ),
    )
    replace_in_environment: list[EnvironmentReplacementModel] = SettingsField(
        default_factory=list,
        title="Replace values in environment",
        description=(
            "Modify environment variable values.\n\n"
            "For example, replace a local path with one valid on the render"
            " nodes."
        ),
    )


class TraitFieldSynonymModel(BaseSettingsModel):
    _layout = "compact"
    name: str = SettingsField(
        "",
        title="Typed name",
        description="Name accepted in the search bar, e.g. 'resolution:width'.",
    )
    field: str = SettingsField(
        "",
        title="Trait field",
        description=(
            "Versionless trait ID and field the name stands for, e.g."
            " 'ayon.2d.PixelBased/display_window_width'."
        ),
    )


class TraitsFilteringModel(BaseSettingsModel):
    """Representation trait filters in the web UI.

    The filter bar offers only the trait fields listed here, and only
    when representations of the project use them. "Has Trait" still
    lists every used trait. The lists only change what the filter bar
    offers, other trait fields still work in API filters.
    """

    exposed_traits: list[str] = SettingsField(
        default_factory=list,
        title="Exposed traits",
        description=(
            "Versionless trait IDs whose fields are all offered in the"
            " filter bar, e.g. 'ayon.2d.PixelBased'."
        ),
    )
    exposed_fields: list[str] = SettingsField(
        default_factory=list,
        title="Exposed fields",
        description=(
            "Single trait fields offered in the filter bar, as"
            " '<versionless trait ID>/<field>', e.g."
            " 'ayon.time.Sequence/frame_padding'."
        ),
    )
    synonyms: list[TraitFieldSynonymModel] = SettingsField(
        default_factory=list,
        title="Synonyms",
        description="Extra names for trait fields in the typed filter syntax.",
    )


class CoreSettings(BaseSettingsModel):
    studio_name: str = SettingsField("", title="Studio name", scope=["studio"])
    studio_code: str = SettingsField("", title="Studio code", scope=["studio"])
    environments: str = SettingsField(
        "{}",
        title="Global environment variables",
        widget="textarea",
        syntax="json",
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
        description=(
            "Map paths per platform on launcher start.\n\n"
            "Makes project files reachable under the same path on every"
            " machine, e.g. map a network share to drive `P:` on Windows."
        ),
    )
    tools: GlobalToolsModel = SettingsField(
        default_factory=GlobalToolsModel,
        title="Tools"
    )
    version_start_category: VersionStartCategoryModel = SettingsField(
        default_factory=VersionStartCategoryModel,
        title="Version start",
        description=(
            "Define version number a new product starts with.\n\n"
            "Applies to both products and workfiles, e.g. start at `v000`"
            " instead of `v001` for some tasks or products."
        ),
    )
    reviewable_layers: ReviewLayersModel = SettingsField(
        default_factory=ReviewLayersModel,
        title="Default reviewable layers",
        description=(
            "Define which layer to use as reviewable.\n\n"
            "Ordered list of layer names used to determine the reviewable"
            " channel. The first matching layer in the list is used. If the"
            " list is empty, review layers use the default sorting behavior."
        ),
    )
    imageio: CoreImageIOBaseModel = SettingsField(
        default_factory=CoreImageIOBaseModel,
        title="Color Management (ImageIO)"
    )
    publish: PublishPuginsModel = SettingsField(
        default_factory=PublishPuginsModel,
        title="Publish plugins"
    )
    workfile_actions: WorkfileActionsModel = SettingsField(
        default_factory=WorkfileActionsModel,
        title="Workfile actions",
        description="Actions available in the Workfiles tool.",
    )
    project_folder_structure: str = SettingsField(
        "{}",
        widget="textarea",
        title="Project folder structure",
        description=(
            "Defines project folders to create on disk"
            " for 'Create project folders' action."
        ),
        syntax="json",
        section="---"
    )
    project_environments: str = SettingsField(
        "{}",
        widget="textarea",
        title="Project environments",
        description=(
            "Environment variables set when launching applications in this"
            " project, as a JSON object."
        ),
        syntax="json",
        section="---"
    )
    filter_env_profiles: list[FilterEnvsProfileModel] = SettingsField(
        default_factory=list,
        title="Filter farm environment",
        description=(
            "Remove or modify environment variables of farm jobs.\n\n"
            "Applies to publish jobs sent to the render farm. The first"
            " profile matching the host, task and folder is used."
        ),
    )
    traits_filtering: TraitsFilteringModel = SettingsField(
        default_factory=TraitsFilteringModel,
        title="Representation trait filters",
        description=(
            "Trait fields offered when filtering representations"
            " in the web UI."
        ),
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
                "app_names": [],
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
    "reviewable_layers": {
        "review_layers": [
            "Beauty"
        ]
    },
    "publish": DEFAULT_PUBLISH_VALUES,
    "workfile_actions": DEFAULT_WORKFILE_ACTIONS_VALUES,
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
    "project_environments": json.dumps(
        {},
        indent=4
    ),
    "filter_env_profiles": [],
    "traits_filtering": {
        "exposed_traits": [
            "ayon.2d.PixelBased",
            "ayon.time.FrameRanged",
            "ayon.time.Handles",
        ],
        "exposed_fields": [],
        "synonyms": [
            {
                "name": "resolution:width",
                "field": "ayon.2d.PixelBased/display_window_width",
            },
            {
                "name": "resolution:height",
                "field": "ayon.2d.PixelBased/display_window_height",
            },
        ],
    },
}
