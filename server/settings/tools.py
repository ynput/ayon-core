from pydantic import validator

from ayon_server.lib.postgres import Postgres
from ayon_server.access.access_groups import AccessGroups

from ayon_server.settings import (
    BaseSettingsModel,
    SettingsField,
    normalize_name,
    ensure_unique_names,
    task_types_enum,
    anatomy_template_items_enum
)


class ProductTypeSmartSelectModel(BaseSettingsModel):
    _layout = "expanded"
    name: str = SettingsField("", title="Product type")
    task_names: list[str] = SettingsField(
        default_factory=list, title="Task names"
    )

    @validator("name")
    def normalize_value(cls, value):
        return normalize_name(value)


class ProductNameProfile(BaseSettingsModel):
    _layout = "expanded"

    product_base_types: list[str] = SettingsField(
        default_factory=list,
        title="Product base types",
    )
    product_types: list[str] = SettingsField(
        default_factory=list,
        title="Product types",
    )
    host_names: list[str] = SettingsField(
        default_factory=list,
        title="Host names",
    )
    task_types: list[str] = SettingsField(
        default_factory=list,
        title="Task types",
        enum_resolver=task_types_enum,
    )
    task_names: list[str] = SettingsField(
        default_factory=list,
        title="Task names",
    )
    template: str = SettingsField(
        "",
        title="Template",
        regex=r"^[<>{}\[\]a-zA-Z0-9_.]+$",
    )


class FilterCreatorProfile(BaseSettingsModel):
    """Provide list of allowed Creator identifiers for context"""

    _layout = "expanded"
    host_names: list[str] = SettingsField(
        default_factory=list, title="Host names"
    )
    task_types: list[str] = SettingsField(
        default_factory=list,
        title="Task types",
        enum_resolver=task_types_enum
    )
    task_names: list[str] = SettingsField(
        default_factory=list,
        title="Task names")
    creator_labels: list[str] = SettingsField(
        default_factory=list,
        title="Allowed Creator Labels",
        description="Copy creator label from Publisher, regex supported."
    )


class CreatorToolModel(BaseSettingsModel):
    # TODO this was dynamic dictionary '{name: task_names}'
    product_types_smart_select: list[ProductTypeSmartSelectModel] = (
        SettingsField(
            default_factory=list,
            title="Create Smart Select"
        )
    )
    # TODO: change to False in next releases
    use_legacy_product_names_for_renders: bool = SettingsField(
        True,
        title="Use legacy product names for renders",
        description="Use product naming templates for renders. "
                    "This is for backwards compatibility enabled by default."
                    "When enabled, it will ignore any templates for renders "
                    "that are set in the product name profiles.")

    product_name_profiles: list[ProductNameProfile] = SettingsField(
        default_factory=list,
        title="Product name profiles"
    )

    filter_creator_profiles: list[FilterCreatorProfile] = SettingsField(
        default_factory=list,
        title="Filter creator profiles",
        description="Allowed list of creator labels that will be only shown"
                    " if profile matches context."
    )

    @validator("product_types_smart_select")
    def validate_unique_name(cls, value):
        ensure_unique_names(value)
        return value


class WorkfileTemplateProfile(BaseSettingsModel):
    _layout = "expanded"
    task_types: list[str] = SettingsField(
        default_factory=list,
        title="Task types",
        enum_resolver=task_types_enum
    )
    # TODO this should use hosts enum
    host_names: list[str] = SettingsField(
        default_factory=list,
        title="Host names",
    )
    # TODO this was using project anatomy template name
    workfile_template: str = SettingsField("", title="Workfile template")


class LastWorkfileOnStartupProfile(BaseSettingsModel):
    _layout = "expanded"
    # TODO this should use hosts enum
    host_names: list[str] = SettingsField(
        default_factory=list,
        title="Host names",
    )
    task_types: list[str] = SettingsField(
        default_factory=list,
        title="Task types",
        enum_resolver=task_types_enum
    )
    task_names: list[str] = SettingsField(
        default_factory=list,
        title="Task names",
    )
    enabled: bool = SettingsField(True, title="Enabled")
    use_last_published_workfile: bool = SettingsField(
        True, title="Use last published workfile"
    )


class WorkfilesToolOnStartupProfile(BaseSettingsModel):
    _layout = "expanded"
    # TODO this should use hosts enum
    host_names: list[str] = SettingsField(
        default_factory=list,
        title="Host names",
    )
    task_types: list[str] = SettingsField(
        default_factory=list,
        title="Task types",
        enum_resolver=task_types_enum
    )
    task_names: list[str] = SettingsField(
        default_factory=list,
        title="Task names",
    )
    enabled: bool = SettingsField(True, title="Enabled")


class ExtraWorkFoldersProfile(BaseSettingsModel):
    _layout = "expanded"
    # TODO this should use hosts enum
    host_names: list[str] = SettingsField(
        default_factory=list,
        title="Host names",
    )
    task_types: list[str] = SettingsField(
        default_factory=list,
        title="Task types",
        enum_resolver=task_types_enum
    )
    task_names: list[str] = SettingsField(
        default_factory=list, title="Task names"
    )
    folders: list[str] = SettingsField(default_factory=list, title="Folders")


class WorkfilesLockProfile(BaseSettingsModel):
    _layout = "expanded"
    # TODO this should use hosts enum
    host_names: list[str] = SettingsField(
        default_factory=list,
        title="Host names",
    )
    enabled: bool = SettingsField(True, title="Enabled")


class AYONMenuModel(BaseSettingsModel):
    _layout = "expanded"
    version_up_current_workfile: bool = SettingsField(
        False,
        title="Version Up Workfile",
        description="Add 'Version Up Workfile' to AYON menu"
    )


class WorkfilesToolModel(BaseSettingsModel):
    workfile_template_profiles: list[WorkfileTemplateProfile] = SettingsField(
        default_factory=list,
        title="Workfile template profiles"
    )
    last_workfile_on_startup: list[LastWorkfileOnStartupProfile] = (
        SettingsField(
            default_factory=list,
            title="Open last workfile on launch"
        )
    )
    open_workfile_tool_on_startup: list[WorkfilesToolOnStartupProfile] = (
        SettingsField(
            default_factory=list,
            title="Open workfile tool on launch"
        )
    )
    extra_folders: list[ExtraWorkFoldersProfile] = SettingsField(
        default_factory=list,
        title="Extra work folders"
    )
    workfile_lock_profiles: list[WorkfilesLockProfile] = SettingsField(
        default_factory=list,
        title="Workfile lock profiles"
    )


def _product_types_enum():
    return [
        "action",
        "animation",
        "assembly",
        "audio",
        "backgroundComp",
        "backgroundLayout",
        "camera",
        "editorial",
        "gizmo",
        "image",
        "imagesequence",
        "layout",
        "look",
        "matchmove",
        "mayaScene",
        "model",
        "nukenodes",
        "plate",
        "pointcache",
        "prerender",
        "redshiftproxy",
        "reference",
        "render",
        "review",
        "rig",
        "setdress",
        "take",
        "usd",
        "vdbcache",
        "vrayproxy",
        "workfile",
        "xgen",
        "yetiRig",
        "yeticache"
    ]


def filter_type_enum():
    return [
        {"value": "is_allow_list", "label": "Allow list"},
        {"value": "is_deny_list", "label": "Deny list"},
    ]


class LoaderProductTypeFilterProfile(BaseSettingsModel):
    _layout = "expanded"
    # TODO this should use hosts enum
    host_names: list[str] = SettingsField(
        default_factory=list,
        title="Host names",
    )
    task_types: list[str] = SettingsField(
        default_factory=list,
        title="Task types",
        enum_resolver=task_types_enum
    )
    filter_type: str = SettingsField(
        "is_allow_list",
        title="Filter type",
        section="Product type filter",
        enum_resolver=filter_type_enum
    )
    filter_product_types: list[str] = SettingsField(
        default_factory=list,
        title="Product types",
        enum_resolver=_product_types_enum
    )


def _filter_mode_enum():
    return [
        {"value": "allowlist", "label": "Allowlist"},
        {"value": "denylist", "label": "Denylist"},
    ]


USERS_QUERY = """
    SELECT name, attrib, data FROM public.users
    ORDER BY COALESCE(attrib->>'fullName', name)
"""

async def _users_enum(project_name) -> list[dict]:
    # TODO use users enum registry
    # - there is a bug, artist users are not returned when
    #   project_name is None
    # return await EnumRegistry.resolve("users")

    result = []

    async with Postgres.transaction():
        stmt = await Postgres.prepare(USERS_QUERY)
        async for row in stmt.cursor():
            name, attrib, udata = row

            is_admin = udata.get("isAdmin", False)
            is_manager = udata.get("isManager", False)

            if project_name and not (is_admin or is_manager):
                ags = udata.get("accessGroups", {}).get(project_name, [])
                if not ags:
                    continue

            result.append({
                "value": name,
                "label": attrib.get("fullName") or name,
            })
    return result


async def _access_groups_enum(project_name: str) -> list[str]:
    if not project_name:
        output = {
            name
            for name, _ in AccessGroups.access_groups
        }
        return list(sorted(output))

    output = set()
    for name, project in AccessGroups.access_groups:
        if project in ("_", project_name):
            output.add(name)
    return list(sorted(output))


class ProductGroupEditingModel(BaseSettingsModel):
    groups_filter_mode: str = SettingsField(
        "denylist",
        enum_resolver=_filter_mode_enum,
        section="Access groups",
        title="Access groups filter mode",
        description="Filter mode for Access groups.",
    )
    access_groups: list[str] = SettingsField(
        default_factory=list,
        title="Access groups",
        description="List of access groups that will be used for filtering.",
        enum_resolver=_access_groups_enum,
    )
    users_filter_mode: str = SettingsField(
        "allowlist",
        section="Users",
        enum_resolver=_filter_mode_enum,
        title="Users filter mode",
        description=(
            "Filter mode for users. Users filtering has priority"
            " over User groups."
        ),
    )
    usernames: list[str] = SettingsField(
        default_factory=list,
        title="Users",
        description="List of users that will be used for filtering.",
        enum_resolver=_users_enum,
    )


class ProductGroupLoaderSettings(BaseSettingsModel):
    group_editing: ProductGroupEditingModel = SettingsField(
        default_factory=ProductGroupEditingModel,
        title="Allow product group editing",
    )


class LoaderToolModel(BaseSettingsModel):
    product_type_filter_profiles: list[LoaderProductTypeFilterProfile] = (
        SettingsField(default_factory=list, title="Product type filtering")
    )
    product_group: ProductGroupLoaderSettings = SettingsField(
        default_factory=ProductGroupLoaderSettings,
        title="Product grouping",
    )


class PublishTemplateNameProfile(BaseSettingsModel):
    _layout = "expanded"
    product_base_types: list[str] = SettingsField(
        default_factory=list,
        title="Product base types"
    )
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
    template_name: str = SettingsField(
        "",
        title="Template name",
        enum_resolver=anatomy_template_items_enum(category="publish")
    )


class HeroTemplateNameProfile(BaseSettingsModel):
    _layout = "expanded"
    product_base_types: list[str] = SettingsField(
        default_factory=list,
        title="Product base types",
    )
    host_names: list[str] = SettingsField(
        default_factory=list,
        title="Host names",
    )
    task_types: list[str] = SettingsField(
        default_factory=list,
        title="Task types",
        enum_resolver=task_types_enum
    )
    task_names: list[str] = SettingsField(
        default_factory=list,
        title="Task names",
    )
    template_name: str = SettingsField(
        "",
        title="Template name",
        enum_resolver=anatomy_template_items_enum(category="hero")
    )


class CustomStagingDirProfileModel(BaseSettingsModel):
    active: bool = SettingsField(True, title="Is active")
    host_names: list[str] = SettingsField(
        default_factory=list,
        title="Host names",
    )
    task_types: list[str] = SettingsField(
        default_factory=list,
        title="Task types",
        enum_resolver=task_types_enum
    )
    task_names: list[str] = SettingsField(
        default_factory=list, title="Task names"
    )
    product_base_types: list[str] = SettingsField(
        default_factory=list, title="Product base types"
    )
    product_names: list[str] = SettingsField(
        default_factory=list, title="Product names"
    )
    custom_staging_dir_persistent: bool = SettingsField(
        False, title="Custom Staging Folder Persistent"
    )
    template_name: str = SettingsField(
        "",
        title="Template name",
        enum_resolver=anatomy_template_items_enum(category="staging")
    )


class DiscoverValidationModel(BaseSettingsModel):
    """Strictly validate publish plugins discovery.

    Artist won't be able to publish if path to publish plugin fails to be
        imported.

    """
    _isGroup = True
    enabled: bool = SettingsField(
        False,
        description="Enable strict mode of plugins discovery",
    )
    ignore_paths: list[str] = SettingsField(
        default_factory=list,
        title="Ignored paths (regex)",
        description=(
            "Paths that do match regex will be skipped in validation."
        ),
    )


class PublishToolModel(BaseSettingsModel):
    template_name_profiles: list[PublishTemplateNameProfile] = SettingsField(
        default_factory=list,
        title="Template name profiles"
    )
    hero_template_name_profiles: list[HeroTemplateNameProfile] = (
        SettingsField(
            default_factory=list,
            title="Hero template name profiles"
        )
    )
    custom_staging_dir_profiles: list[CustomStagingDirProfileModel] = (
        SettingsField(
            default_factory=list,
            title="Custom Staging Dir Profiles"
        )
    )
    discover_validation: DiscoverValidationModel = SettingsField(
        default_factory=DiscoverValidationModel,
        title="Validate plugins discovery",
    )
    comment_minimum_required_chars: int = SettingsField(
        0,
        title="Publish comment minimum required characters",
        description=(
            "Minimum number of characters required in the comment field "
            "before the publisher UI is allowed to continue publishing"
        )
    )


class GlobalToolsModel(BaseSettingsModel):
    ayon_menu: AYONMenuModel = SettingsField(
        default_factory=AYONMenuModel,
        title="AYON Menu"
    )
    creator: CreatorToolModel = SettingsField(
        default_factory=CreatorToolModel,
        title="Creator"
    )
    Workfiles: WorkfilesToolModel = SettingsField(
        default_factory=WorkfilesToolModel,
        title="Workfiles"
    )
    loader: LoaderToolModel = SettingsField(
        default_factory=LoaderToolModel,
        title="Loader"
    )
    publish: PublishToolModel = SettingsField(
        default_factory=PublishToolModel,
        title="Publish"
    )


DEFAULT_TOOLS_VALUES = {
    "ayon_menu": {
        "version_up_current_workfile": False
    },
    "creator": {
        "product_types_smart_select": [
            {
                "name": "Render",
                "task_names": [
                    "light",
                    "render"
                ]
            },
            {
                "name": "Model",
                "task_names": [
                    "model"
                ]
            },
            {
                "name": "Layout",
                "task_names": [
                    "layout"
                ]
            },
            {
                "name": "Look",
                "task_names": [
                    "look"
                ]
            },
            {
                "name": "Rig",
                "task_names": [
                    "rigging",
                    "rig"
                ]
            }
        ],
        "product_name_profiles": [
            {
                "product_base_types": [],
                "product_types": [],
                "host_names": [],
                "task_types": [],
                "task_names": [],
                "template": "{product[type]}{variant}"
            },
            {
                "product_base_types": [
                    "workfile"
                ],
                "product_types": [],
                "host_names": [],
                "task_types": [],
                "task_names": [],
                "template": "{product[type]}{Task[name]}"
            },
            {
                "product_base_types": [
                    "render"
                ],
                "product_types": [],
                "host_names": [],
                "task_types": [],
                "task_names": [],
                "template": "{product[type]}{Task[name]}{Variant}<_{Aov}>"
            },
            {
                "product_base_types": [
                    "renderLayer",
                    "renderPass"
                ],
                "product_types": [],
                "host_names": [
                    "tvpaint"
                ],
                "task_types": [],
                "task_names": [],
                "template": (
                    "{product[type]}{Task[name]}_{Renderlayer}_{Renderpass}"
                )
            },
            {
                "product_base_types": [
                    "review",
                    "workfile"
                ],
                "product_types": [],
                "host_names": [
                    "aftereffects",
                    "tvpaint"
                ],
                "task_types": [],
                "task_names": [],
                "template": "{product[type]}{Task[name]}"
            },
            {
                "product_base_types": ["render"],
                "product_types": [],
                "host_names": [
                    "aftereffects"
                ],
                "task_types": [],
                "task_names": [],
                "template": "{product[type]}{Task[name]}{Composition}{Variant}"
            },
            {
                "product_base_types": [
                    "staticMesh"
                ],
                "product_types": [],
                "host_names": [
                    "maya"
                ],
                "task_types": [],
                "task_names": [],
                "template": "S_{folder[name]}{variant}"
            },
            {
                "product_base_types": [
                    "skeletalMesh"
                ],
                "product_types": [],
                "host_names": [
                    "maya"
                ],
                "task_types": [],
                "task_names": [],
                "template": "SK_{folder[name]}{variant}"
            },
            {
                "product_base_types": [
                    "hda"
                ],
                "product_types": [],
                "host_names": [
                    "houdini"
                ],
                "task_types": [],
                "task_names": [],
                "template": "{folder[name]}_{variant}"
            },
            {
                "product_base_types": [
                    "textureSet"
                ],
                "product_types": [],
                "host_names": [
                    "substancedesigner"
                ],
                "task_types": [],
                "task_names": [],
                "template": "T_{folder[name]}{variant}"
            }
        ],
        "filter_creator_profiles": []
    },
    "Workfiles": {
        "workfile_template_profiles": [
            {
                "task_types": [],
                "host_names": [],
                "workfile_template": "default"
            },
            {
                "task_types": [],
                "host_names": [
                    "unreal"
                ],
                "workfile_template": "unreal"
            }
        ],
        "last_workfile_on_startup": [
            {
                "host_names": [],
                "task_types": [],
                "task_names": [],
                "enabled": True,
                "use_last_published_workfile": False
            }
        ],
        "open_workfile_tool_on_startup": [
            {
                "host_names": [],
                "task_types": [],
                "task_names": [],
                "enabled": False
            }
        ],
        "extra_folders": [],
        "workfile_lock_profiles": []
    },
    "loader": {
        "product_type_filter_profiles": []
    },
    "publish": {
        "template_name_profiles": [
            {
                "product_base_types": [],
                "host_names": [],
                "task_types": [],
                "task_names": [],
                "template_name": "default"
            },
            {
                "product_base_types": [
                    "review",
                    "render",
                    "prerender"
                ],
                "host_names": [],
                "task_types": [],
                "task_names": [],
                "template_name": "render"
            },
            {
                "product_base_types": [
                    "image",
                    "textures",
                ],
                "host_names": [
                    "substancedesigner"
                ],
                "task_types": [],
                "task_names": [],
                "template_name": "simpleUnrealTexture"
            },
            {
                "product_base_types": [
                    "staticMesh",
                    "skeletalMesh"
                ],
                "host_names": [
                    "maya"
                ],
                "task_types": [],
                "task_names": [],
                "template_name": "maya2unreal"
            },
            {
                "product_base_types": [
                    "online"
                ],
                "host_names": [
                    "traypublisher"
                ],
                "task_types": [],
                "task_names": [],
                "template_name": "online"
            },
            {
                "product_base_types": [
                    "tycache"
                ],
                "host_names": [
                    "max"
                ],
                "task_types": [],
                "task_names": [],
                "template_name": "tycache"
            },
            {
                "product_base_types": [
                    "uasset",
                    "umap"
                ],
                "host_names": [
                    "unreal"
                ],
                "task_types": [],
                "task_names": [],
                "template_name": "unrealuasset"
            }
        ],
        "hero_template_name_profiles": [
            {
                "product_base_types": [
                    "image",
                    "textures"
                ],
                "host_names": [
                    "substancedesigner"
                ],
                "task_types": [],
                "task_names": [],
                "template_name": "simpleUnrealTextureHero"
            }
        ],
        "discover_validation": {
            "enabled": False,
            "ignore_paths": [],
        },
        "comment_minimum_required_chars": 0,
    }
}
