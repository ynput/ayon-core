from ayon_server.settings import BaseSettingsModel, SettingsField


class ChannelMappingItemModel(BaseSettingsModel):
    _layout = "compact"
    name: str = SettingsField(title="Channel Type")
    value: str = SettingsField(title="Channel Map")


class CreateTextureModel(BaseSettingsModel):
    channel_mapping: list[ChannelMappingItemModel] = SettingsField(
        default_factory=list, title="Channel Mapping")


class CreatorsModel(BaseSettingsModel):
    CreateTextures: CreateTextureModel = SettingsField(
        default_factory=CreateTextureModel,
        title="Create Textures"
    )


DEFAULT_CREATOR_SETTINGS = {
    "CreateTextures": {
        "channel_mapping": [
            {"name": "Base Color", "value": "BaseColor"},
            {"name": "Metallic", "value": "Metallic"},
            {"name": "Roughness", "value": "Roughness"},
            {"name": "Normal", "value": "Normal"},
            {"name": "Height", "value": "Height"},
            {"name": "Specular Edge Color",
             "value": "SpecularEdgeColor"},
            {"name": "Opacity", "value": "Opacity"},
            {"name": "Displacement", "value": "Displacement"},
            {"name": "Glossiness", "value": "Glossiness"},
            {"name": "Anisotropy Level",
             "value": "Anisotropylevel"},
            {"name": "Ambient Occulsion", "value": "AO"},
            {"name": "Anisotropy Angle",
             "value": "Anisotropyangle"},
            {"name": "Transmissive", "value": "Transmissive"},
            {"name": "Reflection", "value": "Reflection"},
            {"name": "Diffuse", "value": "Diffuse"},
            {"name": "Index of Refraction", "value": "Ior"},
            {"name": "Specular Level", "value": "Specularlevel"},
            {"name": "Blending Mask", "value": "BlendingMask"},
            {"name": "Translucency", "value": "Translucency"},
            {"name": "Scattering", "value": "Scattering"},
            {"name": "Scatter Color", "value": "ScatterColor"},
            {"name": "Sheen Opacity", "value": "SheenOpacity"},
            {"name": "Sheen Color", "value": "SheenColor"},
            {"name": "Coat Opacity", "value": "CoatOpacity"},
            {"name": "Coat Color", "value": "CoatColor"},
            {"name": "Coat Roughness", "value": "CoatRoughness"},
            {"name": "CoatSpecularLevel",
             "value": "Coat Specular Level"},
            {"name": "CoatNormal", "value": "Coat Normal"}
        ],
    }
}