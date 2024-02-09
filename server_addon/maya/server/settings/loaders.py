from ayon_server.settings import BaseSettingsModel, SettingsField
from ayon_server.types import ColorRGB_float


class ColorsSetting(BaseSettingsModel):
    model: ColorRGB_float = SettingsField(
        (
            0.8196078431372549,
            0.5176470588235295,
            0.11764705882352941
        ),
        title="Model:"
    )
    rig: ColorRGB_float = SettingsField(
        (
            0.23137254901960785,
            0.8862745098039215,
            0.9215686274509803
        ),
        title="Rig:"
    )
    pointcache: ColorRGB_float = SettingsField(
        (
            0.3686274509803922,
            0.8196078431372549,
            0.11764705882352941
        ),
        title="Pointcache:"
    )
    animation: ColorRGB_float = SettingsField(
        (
            0.3686274509803922,
            0.8196078431372549,
            0.11764705882352941
        ),
        title="Animation:"
    )
    ass: ColorRGB_float = SettingsField(
        (
            0.9764705882352941,
            0.5294117647058824,
            0.20784313725490197
        ),
        title="Arnold StandIn:"
    )
    camera: ColorRGB_float = SettingsField(
        (
            0.5333333333333333,
            0.4470588235294118,
            0.9568627450980393
        ),
        title="Camera:"
    )
    fbx: ColorRGB_float = SettingsField(
        (
            0.8431372549019608,
            0.6509803921568628,
            1.0
        ),
        title="FBX:"
    )
    mayaAscii: ColorRGB_float = SettingsField(
        (
            0.2627450980392157,
            0.6823529411764706,
            1.0
        ),
        title="Maya Ascii:"
    )
    mayaScene: ColorRGB_float = SettingsField(
        (
            0.2627450980392157,
            0.6823529411764706,
            1.0
        ),
        title="Maya Scene:"
    )
    setdress: ColorRGB_float = SettingsField(
        (
            1.0,
            0.9803921568627451,
            0.35294117647058826
        ),
        title="Set Dress:"
    )
    layout: ColorRGB_float = SettingsField(
        (
            1.0,
            0.9803921568627451,
            0.35294117647058826
        ),
        title="Layout:"
    )
    vdbcache: ColorRGB_float = SettingsField(
        (
            0.9764705882352941,
            0.21176470588235294,
            0.0
        ),
        title="VDB Cache:"
    )
    vrayproxy: ColorRGB_float = SettingsField(
        (
            1.0,
            0.5882352941176471,
            0.047058823529411764
        ),
        title="VRay Proxy:"
    )
    vrayscene_layer: ColorRGB_float = SettingsField(
        (
            1.0,
            0.5882352941176471,
            0.047058823529411764
        ),
        title="VRay Scene:"
    )
    yeticache: ColorRGB_float = SettingsField(
        (
            0.38823529411764707,
            0.807843137254902,
            0.8627450980392157
        ),
        title="Yeti Cache:"
    )
    yetiRig: ColorRGB_float = SettingsField(
        (
            0.0,
            0.803921568627451,
            0.49019607843137253
        ),
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
        "model": [
            0.8196078431372549,
            0.5176470588235295,
            0.11764705882352941
        ],
        "rig": [
            0.23137254901960785,
            0.8862745098039215,
            0.9215686274509803
        ],
        "pointcache": [
            0.3686274509803922,
            0.8196078431372549,
            0.11764705882352941
        ],
        "animation": [
            0.3686274509803922,
            0.8196078431372549,
            0.11764705882352941
        ],
        "ass": [
            0.9764705882352941,
            0.5294117647058824,
            0.20784313725490197
        ],
        "camera": [
            0.5333333333333333,
            0.4470588235294118,
            0.9568627450980393
        ],
        "fbx": [
            0.8431372549019608,
            0.6509803921568628,
            1.0
        ],
        "mayaAscii": [
            0.2627450980392157,
            0.6823529411764706,
            1.0
        ],
        "mayaScene": [
            0.2627450980392157,
            0.6823529411764706,
            1.0
        ],
        "setdress": [
            1.0,
            0.9803921568627451,
            0.35294117647058826
        ],
        "layout": [
            1.0,
            0.9803921568627451,
            0.35294117647058826
        ],
        "vdbcache": [
            0.9764705882352941,
            0.21176470588235294,
            0.0
        ],
        "vrayproxy": [
            1.0,
            0.5882352941176471,
            0.047058823529411764
        ],
        "vrayscene_layer": [
            1.0,
            0.5882352941176471,
            0.047058823529411764
        ],
        "yeticache": [
            0.38823529411764707,
            0.807843137254902,
            0.8627450980392157
        ],
        "yetiRig": [
            0.0,
            0.803921568627451,
            0.49019607843137253
        ]
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
