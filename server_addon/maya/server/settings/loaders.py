from ayon_server.settings import BaseSettingsModel, SettingsField
from ayon_server.types import ColorRGB_float


class ColorsSetting(BaseSettingsModel):
    model: ColorRGB_float = SettingsField(
        (0.82, 0.52, 0.12),
        title="Model:"
    )
    rig: ColorRGB_float = SettingsField(
        (0.23, 0.89, 0.92),
        title="Rig:"
    )
    pointcache: ColorRGB_float = SettingsField(
        (0.37, 0.82, 0.12),
        title="Pointcache:"
    )
    animation: ColorRGB_float = SettingsField(
        (0.37, 0.82, 0.12),
        title="Animation:"
    )
    ass: ColorRGB_float = SettingsField(
        (0.98, 0.53, 0.21),
        title="Arnold StandIn:"
    )
    camera: ColorRGB_float = SettingsField(
        (0.53, 0.45, 0.96),
        title="Camera:"
    )
    fbx: ColorRGB_float = SettingsField(
        (0.84, 0.65, 1.0),
        title="FBX:"
    )
    mayaAscii: ColorRGB_float = SettingsField(
        (0.26, 0.68, 1.0),
        title="Maya Ascii:"
    )
    mayaScene: ColorRGB_float = SettingsField(
        (0.26, 0.68, 1.0),
        title="Maya Scene:"
    )
    setdress: ColorRGB_float = SettingsField(
        (1.0, 0.98, 0.35),
        title="Set Dress:"
    )
    layout: ColorRGB_float = SettingsField(
        (1.0, 0.98, 0.35),
        title="Layout:"
    )
    vdbcache: ColorRGB_float = SettingsField(
        (0.98, 0.21, 0.0),
        title="VDB Cache:"
    )
    vrayproxy: ColorRGB_float = SettingsField(
        (1.0, 0.59, 0.05),
        title="VRay Proxy:"
    )
    vrayscene_layer: ColorRGB_float = SettingsField(
        (1.0, 0.59, 0.05),
        title="VRay Scene:"
    )
    yeticache: ColorRGB_float = SettingsField(
        (0.39, 0.81, 0.86),
        title="Yeti Cache:"
    )
    yetiRig: ColorRGB_float = SettingsField(
        (0.0, 0.80, 0.49),
        title="Yeti Rig:"
    )


class ReferenceLoaderModel(BaseSettingsModel):
    namespace: str = SettingsField(title="Namespace")
    group_name: str = SettingsField(title="Group name")
    display_handle: bool = SettingsField(
        title="Display Handle On Load References"
    )


class ImportLoaderModel(BaseSettingsModel):
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

DEFAULT_LOADERS_SETTING = {
    "colors": {
        "model": [0.82, 0.52, 0.12],
        "rig": [0.23, 0.89, 0.92],
        "pointcache": [0.37, 0.82, 0.12],
        "animation": [0.37, 0.82, 0.12],
        "ass": [0.98, 0.53, 0.21],
        "camera":[0.53, 0.45, 0.96],
        "fbx": [0.84, 0.65, 1.0],
        "mayaAscii": [0.26, 0.68, 1.0],
        "mayaScene": [0.26, 0.68, 1.0],
        "setdress": [1.0, 0.98, 0.35],
        "layout": [1.0, 0.98, 0.35],
        "vdbcache": [0.98, 0.21, 0.0],
        "vrayproxy": [1.0, 0.59, 0.05],
        "vrayscene_layer": [1.0, 0.59, 0.05],
        "yeticache": [0.39, 0.81, 0.86],
        "yetiRig": [0.0, 0.80, 0.49],
    },
    "reference_loader": {
        "namespace": "{folder[name]}_{product[name]}_##_",
        "group_name": "_GRP",
        "display_handle": True
    },
    "import_loader": {
        "namespace": "{folder[name]}_{product[name]}_##_",
        "group_name": "_GRP",
        "display_handle": True
    }
}
