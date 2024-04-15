from ayon_server.settings import BaseSettingsModel, SettingsField
from ayon_server.types import ColorRGBA_uint8


class LoaderEnabledModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")


class ColorsSetting(BaseSettingsModel):
    model: ColorRGBA_uint8 = SettingsField(
        (209, 132, 30, 1.0), title="Model:")
    rig: ColorRGBA_uint8 = SettingsField(
        (59, 226, 235, 1.0), title="Rig:")
    pointcache: ColorRGBA_uint8 = SettingsField(
        (94, 209, 30, 1.0), title="Pointcache:")
    animation: ColorRGBA_uint8 = SettingsField(
        (94, 209, 30, 1.0), title="Animation:")
    ass: ColorRGBA_uint8 = SettingsField(
        (249, 135, 53, 1.0), title="Arnold StandIn:")
    camera: ColorRGBA_uint8 = SettingsField(
        (136, 114, 244, 1.0), title="Camera:")
    fbx: ColorRGBA_uint8 = SettingsField(
        (215, 166, 255, 1.0), title="FBX:")
    mayaAscii: ColorRGBA_uint8 = SettingsField(
        (67, 174, 255, 1.0), title="Maya Ascii:")
    mayaScene: ColorRGBA_uint8 = SettingsField(
        (67, 174, 255, 1.0), title="Maya Scene:")
    setdress: ColorRGBA_uint8 = SettingsField(
        (255, 250, 90, 1.0), title="Set Dress:")
    layout: ColorRGBA_uint8 = SettingsField((
        255, 250, 90, 1.0), title="Layout:")
    vdbcache: ColorRGBA_uint8 = SettingsField(
        (249, 54, 0, 1.0), title="VDB Cache:")
    vrayproxy: ColorRGBA_uint8 = SettingsField(
        (255, 150, 12, 1.0), title="VRay Proxy:")
    vrayscene_layer: ColorRGBA_uint8 = SettingsField(
        (255, 150, 12, 1.0), title="VRay Scene:")
    yeticache: ColorRGBA_uint8 = SettingsField(
        (99, 206, 220, 1.0), title="Yeti Cache:")
    yetiRig: ColorRGBA_uint8 = SettingsField(
        (0, 205, 125, 1.0), title="Yeti Rig:")
    # model: ColorRGB_float = SettingsField(
    #     (0.82, 0.52, 0.12), title="Model:"
    # )
    # rig: ColorRGB_float = SettingsField(
    #     (0.23, 0.89, 0.92), title="Rig:"
    # )
    # pointcache: ColorRGB_float = SettingsField(
    #     (0.37, 0.82, 0.12), title="Pointcache:"
    # )
    # animation: ColorRGB_float = SettingsField(
    #     (0.37, 0.82, 0.12), title="Animation:"
    # )
    # ass: ColorRGB_float = SettingsField(
    #     (0.98, 0.53, 0.21), title="Arnold StandIn:"
    # )
    # camera: ColorRGB_float = SettingsField(
    #     (0.53, 0.45, 0.96), title="Camera:"
    # )
    # fbx: ColorRGB_float = SettingsField(
    #     (0.84, 0.65, 1.0), title="FBX:"
    # )
    # mayaAscii: ColorRGB_float = SettingsField(
    #     (0.26, 0.68, 1.0), title="Maya Ascii:"
    # )
    # mayaScene: ColorRGB_float = SettingsField(
    #     (0.26, 0.68, 1.0), title="Maya Scene:"
    # )
    # setdress: ColorRGB_float = SettingsField(
    #     (1.0, 0.98, 0.35), title="Set Dress:"
    # )
    # layout: ColorRGB_float = SettingsField(
    #     (1.0, 0.98, 0.35), title="Layout:"
    # )
    # vdbcache: ColorRGB_float = SettingsField(
    #     (0.98, 0.21, 0.0), title="VDB Cache:"
    # )
    # vrayproxy: ColorRGB_float = SettingsField(
    #     (1.0, 0.59, 0.05), title="VRay Proxy:"
    # )
    # vrayscene_layer: ColorRGB_float = SettingsField(
    #     (1.0, 0.59, 0.05), title="VRay Scene:"
    # )
    # yeticache: ColorRGB_float = SettingsField(
    #     (0.39, 0.81, 0.86), title="Yeti Cache:"
    # )
    # yetiRig: ColorRGB_float = SettingsField(
    #     (0.0, 0.80, 0.49), title="Yeti Rig:"
    # )


class ReferenceLoaderModel(BaseSettingsModel):
    namespace: str = SettingsField(title="Namespace")
    group_name: str = SettingsField(title="Group name")
    display_handle: bool = SettingsField(
        title="Display Handle On Load References"
    )


class ImportLoaderModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    namespace: str = SettingsField(title="Namespace")
    group_name: str = SettingsField(title="Group name")


class LoadersModel(BaseSettingsModel):
    colors: ColorsSetting = SettingsField(
        default_factory=ColorsSetting,
        title="Loaded Products Outliner Colors")

    reference_loader: ReferenceLoaderModel = SettingsField(
        default_factory=ReferenceLoaderModel,
        title="Reference Loader"
    )

    import_loader: ImportLoaderModel = SettingsField(
        default_factory=ImportLoaderModel,
        title="Import Loader"
    )

    # Enable/disable loaders
    ArnoldStandinLoader: LoaderEnabledModel = SettingsField(
        default_factory=LoaderEnabledModel,
        title="Arnold Standin Loader"
    )
    AssemblyLoader: LoaderEnabledModel = SettingsField(
        default_factory=LoaderEnabledModel,
        title="Assembly Loader"
    )
    AudioLoader: LoaderEnabledModel = SettingsField(
        default_factory=LoaderEnabledModel,
        title="Audio Loader"
    )
    GpuCacheLoader: LoaderEnabledModel = SettingsField(
        default_factory=LoaderEnabledModel,
        title="GPU Cache Loader"
    )
    FileNodeLoader: LoaderEnabledModel = SettingsField(
        default_factory=LoaderEnabledModel,
        title="File Node (Image) Loader"
    )
    ImagePlaneLoader: LoaderEnabledModel = SettingsField(
        default_factory=LoaderEnabledModel,
        title="Image Plane Loader"
    )
    LookLoader: LoaderEnabledModel = SettingsField(
        default_factory=LoaderEnabledModel,
        title="Look Loader"
    )
    MatchmoveLoader: LoaderEnabledModel = SettingsField(
        default_factory=LoaderEnabledModel,
        title="Matchmove Loader"
    )
    MultiverseUsdLoader: LoaderEnabledModel = SettingsField(
        default_factory=LoaderEnabledModel,
        title="Multiverse USD Loader"
    )
    MultiverseUsdOverLoader: LoaderEnabledModel = SettingsField(
        default_factory=LoaderEnabledModel,
        title="Multiverse USD Override Loader"
    )
    RedshiftProxyLoader: LoaderEnabledModel = SettingsField(
        default_factory=LoaderEnabledModel,
        title="Redshift Proxy Loader"
    )
    RenderSetupLoader: LoaderEnabledModel = SettingsField(
        default_factory=LoaderEnabledModel,
        title="Render Setup Loader"
    )
    LoadVDBtoArnold: LoaderEnabledModel = SettingsField(
        default_factory=LoaderEnabledModel,
        title="VDB to Arnold Loader"
    )
    LoadVDBtoRedShift: LoaderEnabledModel = SettingsField(
        default_factory=LoaderEnabledModel,
        title="VDB to Redshift Loader"
    )
    LoadVDBtoVRay: LoaderEnabledModel = SettingsField(
        default_factory=LoaderEnabledModel,
        title="VDB to V-Ray Loader"
    )
    VRayProxyLoader: LoaderEnabledModel = SettingsField(
        default_factory=LoaderEnabledModel,
        title="Vray Proxy Loader"
    )
    VRaySceneLoader: LoaderEnabledModel = SettingsField(
        default_factory=LoaderEnabledModel,
        title="VrayScene Loader"
    )
    XgenLoader: LoaderEnabledModel = SettingsField(
        default_factory=LoaderEnabledModel,
        title="Xgen Loader"
    )
    YetiCacheLoader: LoaderEnabledModel = SettingsField(
        default_factory=LoaderEnabledModel,
        title="Yeti Cache Loader"
    )
    YetiRigLoader: LoaderEnabledModel = SettingsField(
        default_factory=LoaderEnabledModel,
        title="Yeti Rig Loader"
    )


DEFAULT_LOADERS_SETTING = {
    "colors": {
        "model": [209, 132, 30, 1.0],
        "rig": [59, 226, 235, 1.0],
        "pointcache": [94, 209, 30, 1.0],
        "animation": [94, 209, 30, 1.0],
        "ass": [249, 135, 53, 1.0],
        "camera": [136, 114, 244, 1.0],
        "fbx": [215, 166, 255, 1.0],
        "mayaAscii": [67, 174, 255, 1.0],
        "mayaScene": [67, 174, 255, 1.0],
        "setdress": [255, 250, 90, 1.0],
        "layout": [255, 250, 90, 1.0],
        "vdbcache": [249, 54, 0, 1.0],
        "vrayproxy": [255, 150, 12, 1.0],
        "vrayscene_layer": [255, 150, 12, 1.0],
        "yeticache": [99, 206, 220, 1.0],
        "yetiRig": [0, 205, 125, 1.0]
        # "model": [0.82, 0.52, 0.12],
        # "rig": [0.23, 0.89, 0.92],
        # "pointcache": [0.37, 0.82, 0.12],
        # "animation": [0.37, 0.82, 0.12],
        # "ass": [0.98, 0.53, 0.21],
        # "camera":[0.53, 0.45, 0.96],
        # "fbx": [0.84, 0.65, 1.0],
        # "mayaAscii": [0.26, 0.68, 1.0],
        # "mayaScene": [0.26, 0.68, 1.0],
        # "setdress": [1.0, 0.98, 0.35],
        # "layout": [1.0, 0.98, 0.35],
        # "vdbcache": [0.98, 0.21, 0.0],
        # "vrayproxy": [1.0, 0.59, 0.05],
        # "vrayscene_layer": [1.0, 0.59, 0.05],
        # "yeticache": [0.39, 0.81, 0.86],
        # "yetiRig": [0.0, 0.80, 0.49],
    },
    "reference_loader": {
        "namespace": "{folder[name]}_{product[name]}_##_",
        "group_name": "_GRP",
        "display_handle": True
    },
    "import_loader": {
        "enabled": True,
        "namespace": "{folder[name]}_{product[name]}_##_",
        "group_name": "_GRP",
        "display_handle": True
    },
    "ArnoldStandinLoader": {"enabled": True},
    "AssemblyLoader": {"enabled": True},
    "AudioLoader": {"enabled": True},
    "FileNodeLoader": {"enabled": True},
    "GpuCacheLoader": {"enabled": True},
    "ImagePlaneLoader": {"enabled": True},
    "LookLoader": {"enabled": True},
    "MatchmoveLoader": {"enabled": True},
    "MultiverseUsdLoader": {"enabled": True},
    "MultiverseUsdOverLoader": {"enabled": True},
    "RedshiftProxyLoader": {"enabled": True},
    "RenderSetupLoader": {"enabled": True},
    "LoadVDBtoArnold": {"enabled": True},
    "LoadVDBtoRedShift": {"enabled": True},
    "LoadVDBtoVRay": {"enabled": True},
    "VRayProxyLoader": {"enabled": True},
    "VRaySceneLoader": {"enabled": True},
    "XgenLoader": {"enabled": True},
    "YetiCacheLoader": {"enabled": True},
    "YetiRigLoader": {"enabled": True},
}
