from ayon_server.settings import (
    BaseSettingsModel,
    SettingsField
)


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


class AOVFilterSubmodel(BaseSettingsModel):
    """You should use the same host name you are using for Houdini."""
    host_name: str = SettingsField("", title="Houdini Host name")
    value: list[str] = SettingsField(
        default_factory=list,
        title="AOV regex"
    )


class CollectLocalRenderInstancesModel(BaseSettingsModel):

    use_deadline_aov_filter: bool = SettingsField(
        False,
        title="Use Deadline AOV Filter"
    )

    aov_filter: AOVFilterSubmodel = SettingsField(
        default_factory=AOVFilterSubmodel,
        title="Reviewable products filter"
    )


def product_types_enum():
    return [
        {"value": "camera", "label": "Camera (Abc)"},
        {"value": "pointcache", "label": "PointCache (Abc)/PointCache (Bgeo)"},
        {"value": "review", "label": "Review"},
        {"value": "staticMesh", "label": "Static Mesh (FBX)"},
        {"value": "usd", "label": "USD (experimental)"},
        {"value": "vdbcache", "label": "VDB Cache"},
        {"value": "imagesequence", "label": "Composite (Image Sequence)"},
        {"value": "ass", "label": "Arnold ASS"},
        {"value": "arnold_rop", "label": "Arnold ROP"},
        {"value": "mantra_rop", "label": "Mantra ROP"},
        {"value": "redshiftproxy", "label": "Redshift Proxy"},
        {"value": "redshift_rop", "label": "Redshift ROP"},
        {"value": "karma_rop", "label": "Karma ROP"},
        {"value": "vray_rop", "label": "VRay ROP"},
        {"value": "model", "label": "Model"},
    ]


class CollectFilesForCleaningUpModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    optional: bool = SettingsField(title="Optional")
    active: bool = SettingsField(title="Active")

    families: list[str] = SettingsField(
        default_factory=list,
        enum_resolver=product_types_enum,
        conditionalEnum=True,
        title="Product Types"
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


class BasicEnabledStatesModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    optional: bool = SettingsField(title="Optional")
    active: bool = SettingsField(title="Active")


class PublishPluginsModel(BaseSettingsModel):
    CollectAssetHandles: CollectAssetHandlesModel = SettingsField(
        default_factory=CollectAssetHandlesModel,
        title="Collect Asset Handles",
        section="Collectors"
    )
    CollectChunkSize: CollectChunkSizeModel = SettingsField(
        default_factory=CollectChunkSizeModel,
        title="Collect Chunk Size"
    )
    CollectFilesForCleaningUp: CollectFilesForCleaningUpModel = SettingsField(
        default_factory=CollectFilesForCleaningUpModel,
        title="Collect Files For Cleaning Up."
    )
    CollectLocalRenderInstances: CollectLocalRenderInstancesModel = SettingsField(
        default_factory=CollectLocalRenderInstancesModel,
        title="Collect Local Render Instances"
    )
    ValidateInstanceInContextHoudini: BasicEnabledStatesModel = SettingsField(
        default_factory=BasicEnabledStatesModel,
        title="Validate Instance is in same Context",
        section="Validators")
    ValidateMeshIsStatic: BasicEnabledStatesModel = SettingsField(
        default_factory=BasicEnabledStatesModel,
        title="Validate Mesh is Static")
    ValidateReviewColorspace: BasicEnabledStatesModel = SettingsField(
        default_factory=BasicEnabledStatesModel,
        title="Validate Review Colorspace")
    ValidateSubsetName: BasicEnabledStatesModel = SettingsField(
        default_factory=BasicEnabledStatesModel,
        title="Validate Subset Name")
    ValidateUnrealStaticMeshName: BasicEnabledStatesModel = SettingsField(
        default_factory=BasicEnabledStatesModel,
        title="Validate Unreal Static Mesh Name")
    ValidateWorkfilePaths: ValidateWorkfilePathsModel = SettingsField(
        default_factory=ValidateWorkfilePathsModel,
        title="Validate workfile paths settings")
    ValidateUSDRenderProductPaths: BasicEnabledStatesModel = SettingsField(
        default_factory=BasicEnabledStatesModel,
        title="Validate USD Render Product Paths")
    ExtractActiveViewThumbnail: BasicEnabledStatesModel = SettingsField(
        default_factory=BasicEnabledStatesModel,
        title="Extract Active View Thumbnail",
        section="Extractors"
    )


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
        "families" : []
    },
    "CollectLocalRenderInstances": {
        "use_deadline_aov_filter": False,
        "aov_filter": {
            "host_name": "houdini",
            "value": [
                ".*([Bb]eauty).*"
            ]
        }
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
    },
    "ValidateUSDRenderProductPaths": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ExtractActiveViewThumbnail": {
        "enabled": True,
        "optional": False,
        "active": True
    }
}
