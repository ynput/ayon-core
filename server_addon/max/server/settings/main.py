from ayon_server.settings import BaseSettingsModel, SettingsField
from .imageio import ImageIOSettings
from .render_settings import (
    RenderSettingsModel, DEFAULT_RENDER_SETTINGS
)
from .create_review_settings import (
    CreateReviewModel, DEFAULT_CREATE_REVIEW_SETTINGS
)
from .publishers import (
    PublishersModel, DEFAULT_PUBLISH_SETTINGS
)


def unit_scale_enum():
    """Return enumerator for scene unit scale."""
    return [
        {"label": "mm", "value": "Millimeters"},
        {"label": "cm", "value": "Centimeters"},
        {"label": "m", "value": "Meters"},
        {"label": "km", "value": "Kilometers"}
    ]


class MxpWorkspaceSettings(BaseSettingsModel):
    enabled_project_creation: bool = SettingsField(
        False, title="Enable Project Creation")
    mxp_workspace_script: str = SettingsField(
        title="Max mxp Workspace", widget="textarea"
    )


class UnitScaleSettings(BaseSettingsModel):
    enabled: bool = SettingsField(True, title="Enabled")
    scene_unit_scale: str = SettingsField(
        "Centimeters",
        title="Scene Unit Scale",
        enum_resolver=unit_scale_enum
    )


class PRTAttributesModel(BaseSettingsModel):
    _layout = "compact"
    name: str = SettingsField(title="Name")
    value: str = SettingsField(title="Attribute")


class PointCloudSettings(BaseSettingsModel):
    attribute: list[PRTAttributesModel] = SettingsField(
        default_factory=list, title="Channel Attribute")


class MaxSettings(BaseSettingsModel):
    unit_scale_settings: UnitScaleSettings = SettingsField(
        default_factory=UnitScaleSettings,
        title="Set Unit Scale"
    )
    mxp_workspace: MxpWorkspaceSettings = SettingsField(
        default_factory=MxpWorkspaceSettings,
        title="Max Workspace"
    )
    imageio: ImageIOSettings = SettingsField(
        default_factory=ImageIOSettings,
        title="Color Management (ImageIO)"
    )
    RenderSettings: RenderSettingsModel = SettingsField(
        default_factory=RenderSettingsModel,
        title="Render Settings"
    )
    CreateReview: CreateReviewModel = SettingsField(
        default_factory=CreateReviewModel,
        title="Create Review"
    )
    PointCloud: PointCloudSettings = SettingsField(
        default_factory=PointCloudSettings,
        title="Point Cloud"
    )
    publish: PublishersModel = SettingsField(
        default_factory=PublishersModel,
        title="Publish Plugins")


DEFAULT_MXP_WORKSPACE_SETTINGS = "\n".join((
    '[Directories]',
    'Animations= ./sceneassets/animations',
    'Archives=./archives',
    'AutoBackup=./autoback',
    'BitmapProxies=./proxies',
    'Fluid Simulations=./SimCache',
    'Images=./sceneassets/images',
    'MaxStart=./',
    'Previews=./previews',
    'RenderAssets=./sceneassets/renderassets',
    'RenderOutput= ./renders/3dsmax',
    'Scenes=./',
    'Sounds=./sceneassets/sounds',
    '[XReferenceDirs]',
    'Dir1=./',
    '[BitmapDirs]',
    'Dir1=C:/Program Files/Autodesk/3ds Max 2023/Maps',
    'Dir2=C:/Program Files/Autodesk/3ds Max 2023/Maps/glare',
    'Dir3=C:/Program Files/Autodesk/3ds Max 2023/Maps/adskMtl',
    'Dir4=C:/Program Files/Autodesk/3ds Max 2023/Maps/Noise',
    'Dir5=C:/Program Files/Autodesk/3ds Max 2023/Maps/mental_mill',
    'Dir6=C:/Program Files/Autodesk/3ds Max 2023/Maps/fx',
    'Dir7=C:/Program Files/Autodesk/3ds Max 2023/Maps/Particle Flow Presets',
    '',
))



DEFAULT_VALUES = {
    "unit_scale_settings": {
        "enabled": True,
        "scene_unit_scale": "Centimeters"
    },
    "mxp_workspace": {
        "enabled_project_creation": False,
        "mxp_workspace_script": DEFAULT_MXP_WORKSPACE_SETTINGS
    },
    "RenderSettings": DEFAULT_RENDER_SETTINGS,
    "CreateReview": DEFAULT_CREATE_REVIEW_SETTINGS,
    "PointCloud": {
        "attribute": [
            {"name": "Age", "value": "age"},
            {"name": "Radius", "value": "radius"},
            {"name": "Position", "value": "position"},
            {"name": "Rotation", "value": "rotation"},
            {"name": "Scale", "value": "scale"},
            {"name": "Velocity", "value": "velocity"},
            {"name": "Color", "value": "color"},
            {"name": "TextureCoordinate", "value": "texcoord"},
            {"name": "MaterialID", "value": "matid"},
            {"name": "custFloats", "value": "custFloats"},
            {"name": "custVecs", "value": "custVecs"},
        ]
    },
    "publish": DEFAULT_PUBLISH_SETTINGS

}
