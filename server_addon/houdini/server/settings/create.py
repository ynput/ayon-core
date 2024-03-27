from ayon_server.settings import BaseSettingsModel, SettingsField


# Creator Plugins
class CreatorModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    default_variants: list[str] = SettingsField(
        title="Default Products",
        default_factory=list,
    )
    staging_dir: str = SettingsField(title="Staging Directory")


class CreateArnoldAssModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    default_variants: list[str] = SettingsField(
        title="Default Products",
        default_factory=list,
    )
    ext: str = SettingsField(Title="Extension")
    staging_dir: str = SettingsField(title="Staging Directory")


class CreateArnoldRopModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    default_variants: list[str] = SettingsField(
        title="Default Products",
        default_factory=list,
    )
    render_staging_dir: str = SettingsField(title="Render Staging Directory")
    ass_dir: str = SettingsField(title="Ass Directory")


class CreateKarmaROPModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    default_variants: list[str] = SettingsField(
        title="Default Products",
        default_factory=list,
    )
    render_staging_dir: str = SettingsField(title="Render Staging Directory")
    checkpoint_dir: str = SettingsField(title="Checkpoint Directory")
    usd_dir: str = SettingsField(title="USD Directory")


class CreateMantraROPModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    default_variants: list[str] = SettingsField(
        title="Default Products",
        default_factory=list,
    )
    render_staging_dir: str = SettingsField(title="Render Staging Directory")
    ifd_dir: str = SettingsField(title="IFD Directory")


class CreateRedshiftROPModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    default_variants: list[str] = SettingsField(
        title="Default Products",
        default_factory=list,
    )
    render_staging_dir: str = SettingsField(title="Render Staging Directory")
    rs_dir: str = SettingsField(title="RS Directory")


class CreateVrayROPModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    default_variants: list[str] = SettingsField(
        title="Default Products",
        default_factory=list,
    )
    render_staging_dir: str = SettingsField(title="Render Staging Directory")
    vrscene_dir: str = SettingsField(title="VRay scene Directory")


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
    staging_dir: str = SettingsField(title="Staging Directory")


class CreatePluginsModel(BaseSettingsModel):
    CreateAlembicCamera: CreatorModel = SettingsField(
        default_factory=CreatorModel,
        title="Create Alembic Camera")
    CreateArnoldAss: CreateArnoldAssModel = SettingsField(
        default_factory=CreateArnoldAssModel,
        title="Create Arnold Ass")
    CreateArnoldRop: CreateArnoldRopModel = SettingsField(
        default_factory=CreateArnoldRopModel,
        title="Create Arnold ROP")
    CreateCompositeSequence: CreatorModel = SettingsField(
        default_factory=CreatorModel,
        title="Create Composite (Image Sequence)")
    CreateHDA: CreatorModel = SettingsField(
        default_factory=CreatorModel,
        title="Create Houdini Digital Asset")
    CreateKarmaROP: CreateKarmaROPModel = SettingsField(
        default_factory=CreateKarmaROPModel,
        title="Create Karma ROP")
    CreateMantraIFD: CreatorModel = SettingsField(
        default_factory=CreatorModel,
        title="Create Mantra IFD")
    CreateMantraROP: CreateMantraROPModel = SettingsField(
        default_factory=CreateMantraROPModel,
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
    CreateRedshiftROP: CreateRedshiftROPModel = SettingsField(
        default_factory=CreateRedshiftROPModel,
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
    CreateVrayROP: CreateVrayROPModel = SettingsField(
        default_factory=CreateVrayROPModel,
        title="Create VRay ROP")


DEFAULT_HOUDINI_CREATE_SETTINGS = {
    "CreateAlembicCamera": {
        "enabled": True,
        "default_variants": ["Main"],
        "staging_dir": "$HIP/ayon/{product[name]}/{product[name]}.{ext}"
    },
    "CreateArnoldAss": {
        "enabled": True,
        "default_variants": ["Main"],
        "ext": ".ass",
        "staging_dir": "$HIP/ayon/{product[name]}/{product[name]}.$F4.{ext}"
    },
    "CreateArnoldRop": {
        "enabled": True,
        "default_variants": ["Main"],
        "render_staging_dir": "$HIP/ayon/{product[name]}/render/{product[name]}.$F4.{ext}",
        "ass_dir": "$HIP/ayon/{product[name]}/ass/{product[name]}.$F4.{ext}"
    },
    "CreateCompositeSequence": {
        "enabled": True,
        "default_variants": ["Main"],
        "staging_dir": "$HIP/ayon/{product[name]}/{product[name]}.$F4.{ext}"
    },
    "CreateHDA": {
        "enabled": True,
        "default_variants": ["Main"],
        "staging_dir":  "$HIP/ayon/{product[name]}/{product[name]}.{ext}"
    },
    "CreateKarmaROP": {
        "enabled": True,
        "default_variants": ["Main"],
        "render_staging_dir": "$HIP/ayon/{product[name]}/render/{product[name]}.$F4.{ext}",
        "checkpoint_dir": "$HIP/ayon/{product[name]}/checkpoint/{product[name]}.$F4.{ext}",
        "usd_dir": "$HIP/ayon/{product[name]}/usd/{product[name]}_$RENDERID"
    },
    "CreateMantraIFD": {
        "enabled": True,
        "default_variants": ["Main"],
        "staging_dir": "$HIP/ayon/{product[name]}/{product[name]}.$F4.{ext}"
    },
    "CreateMantraROP": {
        "enabled": True,
        "default_variants": ["Main"],
        "render_staging_dir": "$HIP/ayon/{product[name]}/render/{product[name]}.$F4.{ext}",
        "ifd_dir": "$HIP/ayon/{product[name]}/ifd/{product[name]}.$F4.{ext}"
    },
    "CreatePointCache": {
        "enabled": True,
        "default_variants": ["Main"],
        "staging_dir": "$HIP/ayon/{product[name]}/{product[name]}.{ext}"
    },
    "CreateBGEO": {
        "enabled": True,
        "default_variants": ["Main"],
        "staging_dir": "$HIP/ayon/{product[name]}/{product[name]}.$F4.{ext}"
    },
    "CreateRedshiftProxy": {
        "enabled": True,
        "default_variants": ["Main"],
        "staging_dir": "$HIP/ayon/{product[name]}/{product[name]}.$F4.{ext}"
    },
    "CreateRedshiftROP": {
        "enabled": True,
        "default_variants": ["Main"],
        "render_staging_dir": "$HIP/ayon/{product[name]}/render/{product[name]}.$AOV.$F4.{ext}",
        "rs_dir": "$HIP/ayon/{product[name]}/rs/{product[name]}.$F4.{ext}"
    },
    "CreateReview": {
        "enabled": True,
        "default_variants": ["Main"],
        "staging_dir": "$HIP/ayon/{product[name]}/{product[name]}.$F4.{ext}"
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
        "staging_dir": "$HIP/ayon/{product[name]}/{product[name]}.{ext}"
    },
    "CreateUSD": {
        "enabled": False,
        "default_variants": ["Main"],
        "staging_dir": "$HIP/ayon/{product[name]}/{product[name]}.{ext}"
    },
    "CreateUSDRender": {
        "enabled": False,
        "default_variants": ["Main"],
        "staging_dir": "$HIP/ayon"
    },
    "CreateVDBCache": {
        "enabled": True,
        "default_variants": ["Main"],
        "staging_dir": "$HIP/ayon/{product[name]}/{product[name]}.$F4.{ext}"
    },
    "CreateVrayROP": {
        "enabled": True,
        "default_variants": ["Main"],
        "render_staging_dir": "$HIP/ayon/{product[name]}/render/{product[name]}.$AOV.$F4.{ext}",
        "vrscene_dir": "$HIP/ayon/{product[name]}/vrscene/{product[name]}.$F4.{ext}"
    },
}
