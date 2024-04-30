from typing import Literal
from pydantic import validator
from ayon_server.settings import (
    BaseSettingsModel,
    SettingsField,
    ensure_unique_names,
)

from .common import KnobModel


class NodesModel(BaseSettingsModel):
    _layout = "expanded"
    plugins: list[str] = SettingsField(
        default_factory=list,
        title="Used in plugins"
    )
    nuke_node_class: str = SettingsField(
        title="Nuke Node Class",
    )


class RequiredNodesModel(NodesModel):
    knobs: list[KnobModel] = SettingsField(
        default_factory=list,
        title="Knobs",
    )

    @validator("knobs")
    def ensure_unique_names(cls, value):
        """Ensure name fields within the lists have unique names."""
        ensure_unique_names(value)
        return value


class OverrideNodesModel(NodesModel):
    subsets: list[str] = SettingsField(
        default_factory=list,
        title="Subsets"
    )

    knobs: list[KnobModel] = SettingsField(
        default_factory=list,
        title="Knobs",
    )

    @validator("knobs")
    def ensure_unique_names(cls, value):
        """Ensure name fields within the lists have unique names."""
        ensure_unique_names(value)
        return value


class NodesSetting(BaseSettingsModel):
    required_nodes: list[RequiredNodesModel] = SettingsField(
        title="Plugin required",
        default_factory=list
    )
    override_nodes: list[OverrideNodesModel] = SettingsField(
        title="Plugin's node overrides",
        default_factory=list
    )


def ocio_configs_switcher_enum():
    return [
        {"value": "nuke-default", "label": "nuke-default"},
        {"value": "spi-vfx", "label": "spi-vfx (11)"},
        {"value": "spi-anim", "label": "spi-anim (11)"},
        {"value": "aces_0.1.1", "label": "aces_0.1.1 (11)"},
        {"value": "aces_0.7.1", "label": "aces_0.7.1 (11)"},
        {"value": "aces_1.0.1", "label": "aces_1.0.1 (11)"},
        {"value": "aces_1.0.3", "label": "aces_1.0.3 (11, 12)"},
        {"value": "aces_1.1", "label": "aces_1.1 (12, 13)"},
        {"value": "aces_1.2", "label": "aces_1.2 (13, 14)"},
        {"value": "studio-config-v1.0.0_aces-v1.3_ocio-v2.1",
         "label": "studio-config-v1.0.0_aces-v1.3_ocio-v2.1 (14)"},
        {"value": "cg-config-v1.0.0_aces-v1.3_ocio-v2.1",
         "label": "cg-config-v1.0.0_aces-v1.3_ocio-v2.1 (14)"},
    ]


class WorkfileColorspaceSettings(BaseSettingsModel):
    """Nuke workfile colorspace preset. """

    color_management: Literal["Nuke", "OCIO"] = SettingsField(
        title="Color Management Workflow"
    )

    native_ocio_config: str = SettingsField(
        title="Native OpenColorIO Config",
        description="Switch between native OCIO configs",
        enum_resolver=ocio_configs_switcher_enum,
        conditionalEnum=True
    )

    working_space: str = SettingsField(
        title="Working Space"
    )
    monitor_lut: str = SettingsField(
        title="Thumbnails"
    )
    monitor_out_lut: str = SettingsField(
        title="Monitor Out"
    )
    int_8_lut: str = SettingsField(
        title="8-bit Files"
    )
    int_16_lut: str = SettingsField(
        title="16-bit Files"
    )
    log_lut: str = SettingsField(
        title="Log Files"
    )
    float_lut: str = SettingsField(
        title="Float Files"
    )


class ReadColorspaceRulesItems(BaseSettingsModel):
    _layout = "expanded"

    regex: str = SettingsField("", title="Regex expression")
    colorspace: str = SettingsField("", title="Colorspace")


class RegexInputsModel(BaseSettingsModel):
    inputs: list[ReadColorspaceRulesItems] = SettingsField(
        default_factory=list,
        title="Inputs"
    )


class ViewProcessModel(BaseSettingsModel):
    viewerProcess: str = SettingsField(
        title="Viewer Process Name"
    )
    output_transform: str = SettingsField(
        title="Output Transform"
    )


class ImageIOConfigModel(BaseSettingsModel):
    override_global_config: bool = SettingsField(
        False,
        title="Override global OCIO config"
    )
    filepath: list[str] = SettingsField(
        default_factory=list,
        title="Config path"
    )


class ImageIOFileRuleModel(BaseSettingsModel):
    name: str = SettingsField("", title="Rule name")
    pattern: str = SettingsField("", title="Regex pattern")
    colorspace: str = SettingsField("", title="Colorspace name")
    ext: str = SettingsField("", title="File extension")


class ImageIOFileRulesModel(BaseSettingsModel):
    activate_host_rules: bool = SettingsField(False)
    rules: list[ImageIOFileRuleModel] = SettingsField(
        default_factory=list,
        title="Rules"
    )

    @validator("rules")
    def validate_unique_outputs(cls, value):
        ensure_unique_names(value)
        return value


class ImageIOSettings(BaseSettingsModel):
    """Nuke color management project settings. """
    _isGroup: bool = True

    """# TODO: enhance settings with host api:
    to restructure settings for simplification.

    now: nuke/imageio/viewer/viewerProcess
    future: nuke/imageio/viewer
    """
    activate_host_color_management: bool = SettingsField(
        True, title="Enable Color Management")
    ocio_config: ImageIOConfigModel = SettingsField(
        default_factory=ImageIOConfigModel,
        title="OCIO config"
    )
    file_rules: ImageIOFileRulesModel = SettingsField(
        default_factory=ImageIOFileRulesModel,
        title="File Rules"
    )
    viewer: ViewProcessModel = SettingsField(
        default_factory=ViewProcessModel,
        title="Viewer",
        description="""Viewer profile is used during
        Creation of new viewer node at knob viewerProcess"""
    )

    """# TODO: enhance settings with host api:
    to restructure settings for simplification.

    now: nuke/imageio/baking/viewerProcess
    future: nuke/imageio/baking
    """
    baking: ViewProcessModel = SettingsField(
        default_factory=ViewProcessModel,
        title="Baking",
        description="""Baking profile is used during
        publishing baked colorspace data at knob viewerProcess"""
    )

    workfile: WorkfileColorspaceSettings = SettingsField(
        default_factory=WorkfileColorspaceSettings,
        title="Workfile"
    )

    nodes: NodesSetting = SettingsField(
        default_factory=NodesSetting,
        title="Nodes"
    )
    """# TODO: enhance settings with host api:
    - [ ] no need for `inputs` middle part. It can stay
      directly on `regex_inputs`
    """
    regex_inputs: RegexInputsModel = SettingsField(
        default_factory=RegexInputsModel,
        title="Assign colorspace to read nodes via rules"
    )


DEFAULT_IMAGEIO_SETTINGS = {
    "viewer": {
        "viewerProcess": "ACES/sRGB",
        "output_transform": "ACES/sRGB"
    },
    "baking": {
        "viewerProcess": "ACES/Rec.709",
        "output_transform": "ACES/Rec.709"
    },
    "workfile": {
        "color_management": "OCIO",
        "native_ocio_config": "aces_1.2",
        "working_space": "role_scene_linear",
        "monitor_lut": "ACES/sRGB",
        "monitor_out_lut": "ACES/sRGB",
        "int_8_lut": "role_matte_paint",
        "int_16_lut": "role_texture_paint",
        "log_lut": "role_compositing_log",
        "float_lut": "role_scene_linear"
    },
    "nodes": {
        "required_nodes": [
            {
                "plugins": [
                    "CreateWriteRender"
                ],
                "nuke_node_class": "Write",
                "knobs": [
                    {
                        "type": "text",
                        "name": "file_type",
                        "text": "exr"
                    },
                    {
                        "type": "text",
                        "name": "datatype",
                        "text": "16 bit half"
                    },
                    {
                        "type": "text",
                        "name": "compression",
                        "text": "Zip (1 scanline)"
                    },
                    {
                        "type": "boolean",
                        "name": "autocrop",
                        "boolean": True
                    },
                    {
                        "type": "color_gui",
                        "name": "tile_color",
                        "color_gui": [
                            186,
                            35,
                            35
                        ]
                    },
                    {
                        "type": "text",
                        "name": "channels",
                        "text": "rgb"
                    },
                    {
                        "type": "text",
                        "name": "colorspace",
                        "text": "scene_linear"
                    },
                    {
                        "type": "boolean",
                        "name": "create_directories",
                        "boolean": True
                    }
                ]
            },
            {
                "plugins": [
                    "CreateWritePrerender"
                ],
                "nuke_node_class": "Write",
                "knobs": [
                    {
                        "type": "text",
                        "name": "file_type",
                        "text": "exr"
                    },
                    {
                        "type": "text",
                        "name": "datatype",
                        "text": "16 bit half"
                    },
                    {
                        "type": "text",
                        "name": "compression",
                        "text": "Zip (1 scanline)"
                    },
                    {
                        "type": "boolean",
                        "name": "autocrop",
                        "boolean": True
                    },
                    {
                        "type": "color_gui",
                        "name": "tile_color",
                        "color_gui": [
                            171,
                            171,
                            10
                        ]
                    },
                    {
                        "type": "text",
                        "name": "channels",
                        "text": "rgb"
                    },
                    {
                        "type": "text",
                        "name": "colorspace",
                        "text": "scene_linear"
                    },
                    {
                        "type": "boolean",
                        "name": "create_directories",
                        "boolean": True
                    }
                ]
            },
            {
                "plugins": [
                    "CreateWriteImage"
                ],
                "nuke_node_class": "Write",
                "knobs": [
                    {
                        "type": "text",
                        "name": "file_type",
                        "text": "tiff"
                    },
                    {
                        "type": "text",
                        "name": "datatype",
                        "text": "16 bit"
                    },
                    {
                        "type": "text",
                        "name": "compression",
                        "text": "Deflate"
                    },
                    {
                        "type": "color_gui",
                        "name": "tile_color",
                        "color_gui": [
                            56,
                            162,
                            7
                        ]
                    },
                    {
                        "type": "text",
                        "name": "channels",
                        "text": "rgb"
                    },
                    {
                        "type": "text",
                        "name": "colorspace",
                        "text": "texture_paint"
                    },
                    {
                        "type": "boolean",
                        "name": "create_directories",
                        "boolean": True
                    }
                ]
            }
        ],
        "override_nodes": []
    },
    "regex_inputs": {
        "inputs": [
            {
                "regex": "(beauty).*(?=.exr)",
                "colorspace": "linear"
            }
        ]
    }
}
