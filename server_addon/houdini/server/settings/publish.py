from ayon_server.settings import BaseSettingsModel, SettingsField


# Publish Plugins
class CollectAssetHandlesModel(BaseSettingsModel):
    """Collect Frame Range
    Disable this if you want the publisher to
    ignore start and end handles specified in the
    asset data for publish instances
    """
    use_asset_handles: bool = SettingsField(
        title="Use asset handles")


class CollectChunkSizeModel(BaseSettingsModel):
    """Collect Chunk Size."""
    enabled: bool = SettingsField(title="Enabled")
    optional: bool = SettingsField(title="Optional")
    chunk_size: int = SettingsField(
        title="Frames Per Task")


class CollectFilesForCleaningUpModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    optional: bool = SettingsField(title="Optional")
    active: bool = SettingsField(title="Active")
    intermediate_exported_render: bool = SettingsField(
        title="Include Intermediate Exported Render Files",
        description="Include intermediate exported render scenes for cleanup"
                    " (.idf, .ass, .usd, .rs) for render instances.",
    )
    families: list[str] = SettingsField(
        default_factory=list,
        title="Product Types",
        description="Find a list of all stock product types in "
                    "[Houdini admin docs](https://ayon.ynput.io/docs/addon_houdini_admin)."
    )


class ValidateWorkfilePathsModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    optional: bool = SettingsField(title="Optional")
    node_types: list[str] = SettingsField(
        default_factory=list,
        title="Node Types"
    )
    prohibited_vars: list[str] = SettingsField(
        default_factory=list,
        title="Prohibited Variables"
    )


class BasicValidateModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    optional: bool = SettingsField(title="Optional")
    active: bool = SettingsField(title="Active")


class PublishPluginsModel(BaseSettingsModel):
    CollectAssetHandles: CollectAssetHandlesModel = SettingsField(
        default_factory=CollectAssetHandlesModel,
        title="Collect Asset Handles.",
        section="Collectors"
    )
    CollectChunkSize: CollectChunkSizeModel = SettingsField(
        default_factory=CollectChunkSizeModel,
        title="Collect Chunk Size."
    )
    CollectFilesForCleaningUp:CollectFilesForCleaningUpModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Collect Files For Cleaning Up."
    )
    ValidateContainers: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Latest Containers.",
        section="Validators")
    ValidateInstanceInContextHoudini: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Instance is in same Context.")
    ValidateMeshIsStatic: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Mesh is Static.")
    ValidateReviewColorspace: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Review Colorspace.")
    ValidateSubsetName: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Subset Name.")
    ValidateUnrealStaticMeshName: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Unreal Static Mesh Name.")
    ValidateWorkfilePaths: ValidateWorkfilePathsModel = SettingsField(
        default_factory=ValidateWorkfilePathsModel,
        title="Validate workfile paths settings.")


DEFAULT_HOUDINI_PUBLISH_SETTINGS = {
    "CollectAssetHandles": {
        "use_asset_handles": True
    },
    "CollectChunkSize": {
        "enabled": True,
        "optional": True,
        "chunk_size": 999999
    },
    "CollectFilesForCleaningUp": {
        "enabled": False,
        "optional": True,
        "active": True,
        "intermediate_exported_render": False,
        "families" : []
    },
    "ValidateContainers": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ValidateInstanceInContextHoudini": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ValidateMeshIsStatic": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ValidateReviewColorspace": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ValidateSubsetName": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ValidateUnrealStaticMeshName": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateWorkfilePaths": {
        "enabled": True,
        "optional": True,
        "node_types": [
            "file",
            "alembic"
        ],
        "prohibited_vars": [
            "$HIP",
            "$JOB"
        ]
    }
}
