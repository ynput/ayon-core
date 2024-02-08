from ayon_server.settings import BaseSettingsModel, SettingsField


# Creator Plugins
class CreatorModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    default_variants: list[str] = SettingsField(
        title="Default Products",
        default_factory=list,
    )
    staging_dir: str = SettingsField(title="Staging Dir")


class CreateArnoldAssModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    default_variants: list[str] = SettingsField(
        title="Default Products",
        default_factory=list,
    )
    ext: str = SettingsField(Title="Extension")
    staging_dir: str = SettingsField(title="Staging Dir")


class CreateStaticMeshModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    default_variants: list[str] = SettingsField(
        default_factory=list,
        title="Default Products"
    )
    static_mesh_prefix: str = SettingsField("S", title="Static Mesh Prefix")
    collision_prefixes: list[str] = SettingsField(
        default_factory=list,
        title="Collision Prefixes"
    )
    staging_dir: str = SettingsField(title="Staging Dir")


class CreatePluginsModel(BaseSettingsModel):
    CreateAlembicCamera: CreatorModel = SettingsField(
        default_factory=CreatorModel,
        title="Create Alembic Camera")
    CreateArnoldAss: CreateArnoldAssModel = SettingsField(
        default_factory=CreateArnoldAssModel,
        title="Create Arnold Ass")
    CreateArnoldRop: CreatorModel = SettingsField(
        default_factory=CreatorModel,
        title="Create Arnold ROP")
    CreateCompositeSequence: CreatorModel = SettingsField(
        default_factory=CreatorModel,
        title="Create Composite (Image Sequence)")
    CreateHDA: CreatorModel = SettingsField(
        default_factory=CreatorModel,
        title="Create Houdini Digital Asset")
    CreateKarmaROP: CreatorModel = SettingsField(
        default_factory=CreatorModel,
        title="Create Karma ROP")
    CreateMantraIFD: CreatorModel = SettingsField(
        default_factory=CreatorModel,
        title="Create Mantra IFD")
    CreateMantraROP: CreatorModel = SettingsField(
        default_factory=CreatorModel,
        title="Create Mantra ROP")
    CreatePointCache: CreatorModel = SettingsField(
        default_factory=CreatorModel,
        title="Create PointCache (Abc)")
    CreateBGEO: CreatorModel = SettingsField(
        default_factory=CreatorModel,
        title="Create PointCache (Bgeo)")
    CreateRedshiftProxy: CreatorModel = SettingsField(
        default_factory=CreatorModel,
        title="Create Redshift Proxy")
    CreateRedshiftROP: CreatorModel = SettingsField(
        default_factory=CreatorModel,
        title="Create Redshift ROP")
    CreateReview: CreatorModel = SettingsField(
        default_factory=CreatorModel,
        title="Create Review")
    # "-" is not compatible in the new model
    CreateStaticMesh: CreateStaticMeshModel = SettingsField(
        default_factory=CreateStaticMeshModel,
        title="Create Static Mesh")
    CreateUSD: CreatorModel = SettingsField(
        default_factory=CreatorModel,
        title="Create USD (experimental)")
    CreateUSDRender: CreatorModel = SettingsField(
        default_factory=CreatorModel,
        title="Create USD render (experimental)")
    CreateVDBCache: CreatorModel = SettingsField(
        default_factory=CreatorModel,
        title="Create VDB Cache")
    CreateVrayROP: CreatorModel = SettingsField(
        default_factory=CreatorModel,
        title="Create VRay ROP")


DEFAULT_HOUDINI_CREATE_SETTINGS = {
    "CreateAlembicCamera": {
        "enabled": True,
        "default_variants": ["Main"],
        "staging_dir": "$HIP/ayon"
    },
    "CreateArnoldAss": {
        "enabled": True,
        "default_variants": ["Main"],
        "ext": ".ass",
        "staging_dir": "$HIP/ayon"
    },
    "CreateArnoldRop": {
        "enabled": True,
        "default_variants": ["Main"],
        "staging_dir": "$HIP/ayon"
    },
    "CreateCompositeSequence": {
        "enabled": True,
        "default_variants": ["Main"],
        "staging_dir": "$HIP/ayon"
    },
    "CreateHDA": {
        "enabled": True,
        "default_variants": ["Main"],
        "staging_dir": "$HIP/ayon"
    },
    "CreateKarmaROP": {
        "enabled": True,
        "default_variants": ["Main"],
        "staging_dir": "$HIP/ayon"
    },
    "CreateMantraIFD": {
        "enabled": True,
        "default_variants": ["Main"],
        "staging_dir": "$HIP/ayon"
    },
    "CreateMantraROP": {
        "enabled": True,
        "default_variants": ["Main"],
        "staging_dir": "$HIP/ayon"
    },
    "CreatePointCache": {
        "enabled": True,
        "default_variants": ["Main"],
        "staging_dir": "$HIP/ayon"
    },
    "CreateBGEO": {
        "enabled": True,
        "default_variants": ["Main"],
        "staging_dir": "$HIP/ayon"
    },
    "CreateRedshiftProxy": {
        "enabled": True,
        "default_variants": ["Main"],
        "staging_dir": "$HIP/ayon"
    },
    "CreateRedshiftROP": {
        "enabled": True,
        "default_variants": ["Main"],
        "staging_dir": "$HIP/ayon"
    },
    "CreateReview": {
        "enabled": True,
        "default_variants": ["Main"],
        "staging_dir": "$HIP/ayon"
    },
    "CreateStaticMesh": {
        "enabled": True,
        "default_variants": [
            "Main"
        ],
        "static_mesh_prefix": "S",
        "collision_prefixes": [
            "UBX",
            "UCP",
            "USP",
            "UCX"
        ],
        "staging_dir": "$HIP/ayon"
    },
    "CreateUSD": {
        "enabled": False,
        "default_variants": ["Main"],
        "staging_dir": "$HIP/ayon"
    },
    "CreateUSDRender": {
        "enabled": False,
        "default_variants": ["Main"],
        "staging_dir": "$HIP/ayon"
    },
    "CreateVDBCache": {
        "enabled": True,
        "default_variants": ["Main"],
        "staging_dir": "$HIP/ayon"
    },
    "CreateVrayROP": {
        "enabled": True,
        "default_variants": ["Main"],
        "staging_dir": "$HIP/ayon"
    },
}
