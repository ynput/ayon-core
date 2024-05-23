import json
from pydantic import validator
from ayon_server.settings import (
    BaseSettingsModel,
    SettingsField,
    MultiplatformPathModel,
    ensure_unique_names,
)
from ayon_server.exceptions import BadRequestException
from .publish_playblast import (
    ExtractPlayblastSetting,
    DEFAULT_PLAYBLAST_SETTING,
)


def linear_unit_enum():
    """Get linear units enumerator."""
    return [
        {"label": "mm", "value": "millimeter"},
        {"label": "cm", "value": "centimeter"},
        {"label": "m", "value": "meter"},
        {"label": "km", "value": "kilometer"},
        {"label": "in", "value": "inch"},
        {"label": "ft", "value": "foot"},
        {"label": "yd", "value": "yard"},
        {"label": "mi", "value": "mile"}
    ]


def angular_unit_enum():
    """Get angular units enumerator."""
    return [
        {"label": "deg", "value": "degree"},
        {"label": "rad", "value": "radian"},
    ]


def extract_alembic_data_format_enum():
    return [
        {"label": "ogawa", "value": "ogawa"},
        {"label": "HDF", "value": "HDF"}
    ]


def extract_alembic_overrides_enum():
    return [
        {"label": "Custom Attributes", "value": "attr"},
        {"label": "Custom Attributes Prefix", "value": "attrPrefix"},
        {"label": "Data Format", "value": "dataFormat"},
        {"label": "Euler Filter", "value": "eulerFilter"},
        {"label": "Mel Per Frame Callback", "value": "melPerFrameCallback"},
        {"label": "Mel Post Job Callback", "value": "melPostJobCallback"},
        {"label": "Pre Roll", "value": "preRoll"},
        {"label": "Pre Roll Start Frame", "value": "preRollStartFrame"},
        {
            "label": "Python Per Frame Callback",
            "value": "pythonPerFrameCallback"
        },
        {
            "label": "Python Post Job Callback",
            "value": "pythonPostJobCallback"
        },
        {"label": "Renderable Only", "value": "renderableOnly"},
        {"label": "Strip Namespaces", "value": "stripNamespaces"},
        {"label": "User Attr", "value": "userAttr"},
        {"label": "User Attr Prefix", "value": "userAttrPrefix"},
        {"label": "UV Write", "value": "uvWrite"},
        {"label": "UVs Only", "value": "uvsOnly"},
        {"label": "Verbose", "value": "verbose"},
        {"label": "Visible Only", "value": "visibleOnly"},
        {"label": "Whole Frame Geo", "value": "wholeFrameGeo"},
        {"label": "World Space", "value": "worldSpace"},
        {"label": "Write Color Sets", "value": "writeColorSets"},
        {"label": "Write Creases", "value": "writeCreases"},
        {"label": "Write Face Sets", "value": "writeFaceSets"},
        {"label": "Write Normals", "value": "writeNormals"},
        {"label": "Write UV Sets", "value": "writeUVSets"},
        {"label": "Write Visibility", "value": "writeVisibility"}
    ]


class BasicValidateModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    optional: bool = SettingsField(title="Optional")
    active: bool = SettingsField(title="Active")


class ValidateMeshUVSetMap1Model(BasicValidateModel):
    """Validate model's default uv set exists and is named 'map1'."""
    pass


class ValidateNoAnimationModel(BasicValidateModel):
    """Ensure no keyframes on nodes in the Instance."""
    pass


class ValidateRigOutSetNodeIdsModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="ValidateSkinclusterDeformerSet")
    optional: bool = SettingsField(title="Optional")
    allow_history_only: bool = SettingsField(title="Allow history only")


class ValidateModelNameModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    database: bool = SettingsField(
        title="Use database shader name definitions"
    )
    material_file: MultiplatformPathModel = SettingsField(
        default_factory=MultiplatformPathModel,
        title="Material File",
        description=(
            "Path to material file defining list of material names to check."
        )
    )
    regex: str = SettingsField(
        "(.*)_(\\d)*_(?P<shader>.*)_(GEO)",
        title="Validation regex",
        description=(
            "Regex for validating name of top level group name. You can use"
            " named capturing groups:(?P<asset>.*) for Asset name"
        )
    )
    top_level_regex: str = SettingsField(
        ".*_GRP",
        title="Top level group name regex",
        description=(
            "To check for asset in name so *_some_asset_name_GRP"
            " is valid, use:.*?_(?P<asset>.*)_GEO"
        )
    )


class ValidateModelContentModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    optional: bool = SettingsField(title="Optional")
    validate_top_group: bool = SettingsField(title="Validate one top group")


class ValidateTransformNamingSuffixModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    optional: bool = SettingsField(title="Optional")
    SUFFIX_NAMING_TABLE: str = SettingsField(
        "{}",
        title="Suffix Naming Tables",
        widget="textarea",
        description=(
            "Validates transform suffix based on"
            " the type of its children shapes."
        )
    )

    @validator("SUFFIX_NAMING_TABLE")
    def validate_json(cls, value):
        if not value.strip():
            return "{}"
        try:
            converted_value = json.loads(value)
            success = isinstance(converted_value, dict)
        except json.JSONDecodeError:
            success = False

        if not success:
            raise BadRequestException(
                "The text can't be parsed as json object"
            )
        return value
    ALLOW_IF_NOT_IN_SUFFIX_TABLE: bool = SettingsField(
        title="Allow if suffix not in table"
    )


class CollectMayaRenderModel(BaseSettingsModel):
    sync_workfile_version: bool = SettingsField(
        title="Sync render version with workfile"
    )


class CollectFbxAnimationModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Collect Fbx Animation")


class CollectFbxCameraModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="CollectFbxCamera")


class CollectGLTFModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="CollectGLTF")


class ValidateFrameRangeModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="ValidateFrameRange")
    optional: bool = SettingsField(title="Optional")
    active: bool = SettingsField(title="Active")
    exclude_product_types: list[str] = SettingsField(
        default_factory=list,
        title="Exclude product types"
    )


class ValidateShaderNameModel(BaseSettingsModel):
    """
    Shader name regex can use named capture group asset to validate against current asset name.
    """
    enabled: bool = SettingsField(title="ValidateShaderName")
    optional: bool = SettingsField(title="Optional")
    active: bool = SettingsField(title="Active")
    regex: str = SettingsField(
        "(?P<asset>.*)_(.*)_SHD",
        title="Validation regex"
    )


class ValidateAttributesModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="ValidateAttributes")
    attributes: str = SettingsField(
        "{}", title="Attributes", widget="textarea")

    @validator("attributes")
    def validate_json(cls, value):
        if not value.strip():
            return "{}"
        try:
            converted_value = json.loads(value)
            success = isinstance(converted_value, dict)
        except json.JSONDecodeError:
            success = False

        if not success:
            raise BadRequestException(
                "The attributes can't be parsed as json object"
            )
        return value


class ValidateLoadedPluginModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="ValidateLoadedPlugin")
    optional: bool = SettingsField(title="Optional")
    whitelist_native_plugins: bool = SettingsField(
        title="Whitelist Maya Native Plugins"
    )
    authorized_plugins: list[str] = SettingsField(
        default_factory=list, title="Authorized plugins"
    )


class ValidateMayaUnitsModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="ValidateMayaUnits")
    optional: bool = SettingsField(title="Optional")
    validate_linear_units: bool = SettingsField(title="Validate linear units")
    linear_units: str = SettingsField(
        enum_resolver=linear_unit_enum, title="Linear Units"
    )
    validate_angular_units: bool = SettingsField(
        title="Validate angular units"
    )
    angular_units: str = SettingsField(
        enum_resolver=angular_unit_enum, title="Angular units"
    )
    validate_fps: bool = SettingsField(title="Validate fps")


class ValidateUnrealStaticMeshNameModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="ValidateUnrealStaticMeshName")
    optional: bool = SettingsField(title="Optional")
    validate_mesh: bool = SettingsField(title="Validate mesh names")
    validate_collision: bool = SettingsField(title="Validate collision names")


class ValidateCycleErrorModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="ValidateCycleError")
    optional: bool = SettingsField(title="Optional")
    families: list[str] = SettingsField(
        default_factory=list, title="Families"
    )


class ValidatePluginPathAttributesAttrModel(BaseSettingsModel):
    name: str = SettingsField(title="Node type")
    value: str = SettingsField(title="Attribute")


class ValidatePluginPathAttributesModel(BaseSettingsModel):
    """Fill in the node types and attributes you want to validate.

    <p>e.g. <b>AlembicNode.abc_file</b>, the node type is <b>AlembicNode</b>
    and the node attribute is <b>abc_file</b>
    """

    enabled: bool = SettingsField(title="Enabled")
    optional: bool = SettingsField(title="Optional")
    active: bool = SettingsField(title="Active")
    attribute: list[ValidatePluginPathAttributesAttrModel] = SettingsField(
        default_factory=list,
        title="File Attribute"
    )

    @validator("attribute")
    def validate_unique_outputs(cls, value):
        ensure_unique_names(value)
        return value


# Validate Render Setting
class RendererAttributesModel(BaseSettingsModel):
    _layout = "compact"
    type: str = SettingsField(title="Type")
    value: str = SettingsField(title="Value")


class ValidateRenderSettingsModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    optional: bool = SettingsField(title="Optional")
    active: bool = SettingsField(title="Active")
    arnold_render_attributes: list[RendererAttributesModel] = SettingsField(
        default_factory=list, title="Arnold Render Attributes")
    vray_render_attributes: list[RendererAttributesModel] = SettingsField(
        default_factory=list, title="VRay Render Attributes")
    redshift_render_attributes: list[RendererAttributesModel] = SettingsField(
        default_factory=list, title="Redshift Render Attributes")
    renderman_render_attributes: list[RendererAttributesModel] = SettingsField(
        default_factory=list, title="Renderman Render Attributes")


class BasicValidateModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    optional: bool = SettingsField(title="Optional")
    active: bool = SettingsField(title="Active")


class ValidateCameraContentsModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    optional: bool = SettingsField(title="Optional")
    validate_shapes: bool = SettingsField(title="Validate presence of shapes")


class ExtractProxyAlembicModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    families: list[str] = SettingsField(
        default_factory=list,
        title="Families")


class ExtractAlembicModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    families: list[str] = SettingsField(
        default_factory=list,
        title="Families")
    eulerFilter: bool = SettingsField(
        title="Euler Filter",
        description="Apply Euler filter while sampling rotations."
    )
    renderableOnly: bool = SettingsField(
        title="Renderable Only",
        description="Only export renderable visible shapes."
    )
    stripNamespaces: bool = SettingsField(
        title="Strip Namespaces",
        description=(
            "Namespaces will be stripped off of the node before being written "
            "to Alembic."
        )
    )
    uvsOnly: bool = SettingsField(
        title="UVs Only",
        description=(
            "If this flag is present, only uv data for PolyMesh and SubD "
            "shapes will be written to the Alembic file."
        )
    )
    uvWrite: bool = SettingsField(
        title="UV Write",
        description=(
            "Uv data for PolyMesh and SubD shapes will be written to the "
            "Alembic file."
        )
    )
    verbose: bool = SettingsField(
        title="Verbose",
        description="Prints the current frame that is being evaluated."
    )
    visibleOnly: bool = SettingsField(
        title="Visible Only",
        description="Only export dag objects visible during frame range."
    )
    wholeFrameGeo: bool = SettingsField(
        title="Whole Frame Geo",
        description=(
            "Data for geometry will only be written out on whole frames."
        )
    )
    worldSpace: bool = SettingsField(
        title="World Space",
        description="Any root nodes will be stored in world space."
    )
    writeColorSets: bool = SettingsField(
        title="Write Color Sets",
        description="Write vertex colors with the geometry."
    )
    writeCreases: bool = SettingsField(
        title="Write Creases",
        description="Write the geometry's edge and vertex crease information."
    )
    writeFaceSets: bool = SettingsField(
        title="Write Face Sets",
        description="Write face sets with the geometry."
    )
    writeNormals: bool = SettingsField(
        title="Write Normals",
        description="Write normals with the deforming geometry."
    )
    writeUVSets: bool = SettingsField(
        title="Write UV Sets",
        description=(
            "Write all uv sets on MFnMeshes as vector 2 indexed geometry "
            "parameters with face varying scope."
        )
    )
    writeVisibility: bool = SettingsField(
        title="Write Visibility",
        description=(
            "Visibility state will be stored in the Alembic file. Otherwise "
            "everything written out is treated as visible."
        )
    )
    preRoll: bool = SettingsField(
        title="Pre Roll",
        description=(
            "When enabled, the pre roll start frame is used to pre roll the "
            "When enabled, the pre roll start frame is used to being the "
            "evaluation of the mesh. From the pre roll start frame to the "
            "alembic start frame, will not be written to disk. This can be "
            "used for simulation run up."
        )
    )
    preRollStartFrame: int = SettingsField(
        title="Pre Roll Start Frame",
        description=(
            "The frame to start scene evaluation at.  This is used to set the "
            "starting frame for time dependent translations and can be used to"
            " evaluate run-up that isn't actually translated.\n"
            "NOTE: Pre Roll needs to be enabled for this start frame "
            "to be considered."
        )
    )
    dataFormat: str = SettingsField(
        enum_resolver=extract_alembic_data_format_enum,
        title="Data Format",
        description="The data format to use to write the file."
    )
    bake_attributes: list[str] = SettingsField(
        default_factory=list, title="Bake Attributes",
        description="List of attributes that will be included in the alembic "
                    "export.",
    )
    bake_attribute_prefixes: list[str] = SettingsField(
        default_factory=list, title="Bake Attribute Prefixes",
        description="List of attribute prefixes for attributes that will be "
                    "included in the alembic export.",
    )
    attr: str = SettingsField(
        title="Custom Attributes",
        placeholder="attr1;attr2",
        description=(
            "Attributes matching by name will be included in the Alembic "
            "export. Attributes should be separated by semi-colon `;`"
        )
    )
    attrPrefix: str = SettingsField(
        title="Custom Attributes Prefix",
        placeholder="prefix1;prefix2",
        description=(
            "Attributes starting with these prefixes will be included in the "
            "Alembic export. Attributes should be separated by semi-colon `;`"
        )
    )
    userAttr: str = SettingsField(
        title="User Attr",
        placeholder="attr1;attr2",
        description=(
            "Attributes matching by name will be included in the Alembic "
            "export. Attributes should be separated by semi-colon `;`"
        )
    )
    userAttrPrefix: str = SettingsField(
        title="User Attr Prefix",
        placeholder="prefix1;prefix2",
        description=(
            "Attributes starting with these prefixes will be included in the "
            "Alembic export. Attributes should be separated by semi-colon `;`"
        )
    )
    melPerFrameCallback: str = SettingsField(
        title="Mel Per Frame Callback",
        description=(
            "When each frame (and the static frame) is evaluated the string "
            "specified is evaluated as a Mel command."
        )
    )
    melPostJobCallback: str = SettingsField(
        title="Mel Post Job Callback",
        description=(
            "When the translation has finished the string specified is "
            "evaluated as a Mel command."
        )
    )
    pythonPerFrameCallback: str = SettingsField(
        title="Python Per Frame Callback",
        description=(
            "When each frame (and the static frame) is evaluated the string "
            "specified is evaluated as a python command."
        )
    )
    pythonPostJobCallback: str = SettingsField(
        title="Python Post Job Callback",
        description=(
            "When the translation has finished the string specified is "
            "evaluated as a python command."
        )
    )
    overrides: list[str] = SettingsField(
        enum_resolver=extract_alembic_overrides_enum,
        title="Exposed Overrides",
        description=(
            "Expose the attribute in this list to the user when publishing."
        )
    )


class ExtractObjModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    optional: bool = SettingsField(title="Optional")


class ExtractModelModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    optional: bool = SettingsField(title="Optional")
    active: bool = SettingsField(title="Active")


class ExtractMayaSceneRawModel(BaseSettingsModel):
    """Add loaded instances to those published families:"""
    enabled: bool = SettingsField(title="ExtractMayaSceneRaw")
    add_for_families: list[str] = SettingsField(
        default_factory=list, title="Families"
    )


class ExtractCameraAlembicModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="ExtractCameraAlembic")
    optional: bool = SettingsField(title="Optional")
    active: bool = SettingsField(title="Active")
    bake_attributes: str = SettingsField(
        "[]", title="Bake Attributes", widget="textarea",
        description="List of attributes that will be included in the alembic "
                    "camera export. Needs to be written as a JSON list.",
    )

    @validator("bake_attributes")
    def validate_json_list(cls, value):
        if not value.strip():
            return "[]"
        try:
            converted_value = json.loads(value)
            success = isinstance(converted_value, list)
        except json.JSONDecodeError:
            success = False

        if not success:
            raise BadRequestException(
                "The text can't be parsed as json object"
            )
        return value


class ExtractGLBModel(BaseSettingsModel):
    enabled: bool = True
    active: bool = SettingsField(title="Active")
    ogsfx_path: str = SettingsField(title="GLSL Shader Directory")


class ExtractLookArgsModel(BaseSettingsModel):
    argument: str = SettingsField(title="Argument")
    parameters: list[str] = SettingsField(
        default_factory=list, title="Parameters"
    )


class ExtractLookModel(BaseSettingsModel):
    maketx_arguments: list[ExtractLookArgsModel] = SettingsField(
        default_factory=list,
        title="Extra arguments for maketx command line"
    )


class ExtractGPUCacheModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    optional: bool = SettingsField(title="Optional")
    active: bool = SettingsField(title="Active")
    families: list[str] = SettingsField(default_factory=list, title="Families")
    step: float = SettingsField(1.0, ge=1.0, title="Step")
    stepSave: int = SettingsField(1, ge=1, title="Step Save")
    optimize: bool = SettingsField(title="Optimize Hierarchy")
    optimizationThreshold: int = SettingsField(
        1, ge=1, title="Optimization Threshold"
    )
    optimizeAnimationsForMotionBlur: bool = SettingsField(
        title="Optimize Animations For Motion Blur"
    )
    writeMaterials: bool = SettingsField(title="Write Materials")
    useBaseTessellation: bool = SettingsField(title="User Based Tessellation")


class PublishersModel(BaseSettingsModel):
    CollectMayaRender: CollectMayaRenderModel = SettingsField(
        default_factory=CollectMayaRenderModel,
        title="Collect Render Layers",
        section="Collectors"
    )
    CollectFbxAnimation: CollectFbxAnimationModel = SettingsField(
        default_factory=CollectFbxAnimationModel,
        title="Collect FBX Animation",
    )
    CollectFbxCamera: CollectFbxCameraModel = SettingsField(
        default_factory=CollectFbxCameraModel,
        title="Collect Camera for FBX export",
    )
    CollectGLTF: CollectGLTFModel = SettingsField(
        default_factory=CollectGLTFModel,
        title="Collect Assets for GLB/GLTF export"
    )
    ValidateInstanceInContext: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Instance In Context",
        section="Validators"
    )
    ValidateFrameRange: ValidateFrameRangeModel = SettingsField(
        default_factory=ValidateFrameRangeModel,
        title="Validate Frame Range"
    )
    ValidateShaderName: ValidateShaderNameModel = SettingsField(
        default_factory=ValidateShaderNameModel,
        title="Validate Shader Name"
    )
    ValidateShadingEngine: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Look Shading Engine Naming"
    )
    ValidateMayaColorSpace: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Colorspace"
    )
    ValidateAttributes: ValidateAttributesModel = SettingsField(
        default_factory=ValidateAttributesModel,
        title="Validate Attributes"
    )
    ValidateLoadedPlugin: ValidateLoadedPluginModel = SettingsField(
        default_factory=ValidateLoadedPluginModel,
        title="Validate Loaded Plugin"
    )
    ValidateMayaUnits: ValidateMayaUnitsModel = SettingsField(
        default_factory=ValidateMayaUnitsModel,
        title="Validate Maya Units"
    )
    ValidateUnrealStaticMeshName: ValidateUnrealStaticMeshNameModel = (
        SettingsField(
            default_factory=ValidateUnrealStaticMeshNameModel,
            title="Validate Unreal Static Mesh Name"
        )
    )
    ValidateCycleError: ValidateCycleErrorModel = SettingsField(
        default_factory=ValidateCycleErrorModel,
        title="Validate Cycle Error"
    )
    ValidatePluginPathAttributes: ValidatePluginPathAttributesModel = (
        SettingsField(
            default_factory=ValidatePluginPathAttributesModel,
            title="Plug-in Path Attributes"
        )
    )
    ValidateRenderSettings: ValidateRenderSettingsModel = SettingsField(
        default_factory=ValidateRenderSettingsModel,
        title="Validate Render Settings"
    )
    ValidateResolution: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Resolution Setting"
    )
    ValidateCurrentRenderLayerIsRenderable: BasicValidateModel = (
        SettingsField(
            default_factory=BasicValidateModel,
            title="Validate Current Render Layer Has Renderable Camera"
        )
    )
    ValidateGLSLMaterial: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate GLSL Material"
    )
    ValidateGLSLPlugin: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate GLSL Plugin"
    )
    ValidateRenderImageRule: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Render Image Rule (Workspace)"
    )
    ValidateRenderNoDefaultCameras: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate No Default Cameras Renderable"
    )
    ValidateRenderSingleCamera: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Render Single Camera "
    )
    ValidateRenderLayerAOVs: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Render Passes/AOVs Are Registered"
    )
    ValidateStepSize: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Step Size"
    )
    ValidateVRayDistributedRendering: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="VRay Distributed Rendering"
    )
    ValidateVrayReferencedAOVs: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="VRay Referenced AOVs"
    )
    ValidateVRayTranslatorEnabled: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="VRay Translator Settings"
    )
    ValidateVrayProxy: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="VRay Proxy Settings"
    )
    ValidateVrayProxyMembers: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="VRay Proxy Members"
    )
    ValidateYetiRenderScriptCallbacks: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Yeti Render Script Callbacks"
    )
    ValidateYetiRigCacheState: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Yeti Rig Cache State"
    )
    ValidateYetiRigInputShapesInInstance: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Yeti Rig Input Shapes In Instance"
    )
    ValidateYetiRigSettings: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Yeti Rig Settings"
    )
    # Model - START
    ValidateModelName: ValidateModelNameModel = SettingsField(
        default_factory=ValidateModelNameModel,
        title="Validate Model Name",
        section="Model",
    )
    ValidateModelContent: ValidateModelContentModel = SettingsField(
        default_factory=ValidateModelContentModel,
        title="Validate Model Content",
    )
    ValidateTransformNamingSuffix: ValidateTransformNamingSuffixModel = (
        SettingsField(
            default_factory=ValidateTransformNamingSuffixModel,
            title="Validate Transform Naming Suffix",
        )
    )
    ValidateColorSets: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Color Sets",
    )
    ValidateMeshHasOverlappingUVs: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Mesh Has Overlapping UVs",
    )
    ValidateMeshArnoldAttributes: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Mesh Arnold Attributes",
    )
    ValidateMeshShaderConnections: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Mesh Shader Connections",
    )
    ValidateMeshSingleUVSet: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Mesh Single UV Set",
    )
    ValidateMeshHasUVs: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Mesh Has UVs",
    )
    ValidateMeshLaminaFaces: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Mesh Lamina Faces",
    )
    ValidateMeshNgons: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Mesh Ngons",
    )
    ValidateMeshNonManifold: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Mesh Non-Manifold",
    )
    ValidateMeshNoNegativeScale: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Mesh No Negative Scale",
    )
    ValidateMeshNonZeroEdgeLength: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Mesh Edge Length Non Zero",
    )
    ValidateMeshNormalsUnlocked: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Mesh Normals Unlocked",
    )
    ValidateMeshUVSetMap1: ValidateMeshUVSetMap1Model = SettingsField(
        default_factory=ValidateMeshUVSetMap1Model,
        title="Validate Mesh UV Set Map 1",
    )
    ValidateMeshVerticesHaveEdges: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Mesh Vertices Have Edges",
    )
    ValidateNoAnimation: ValidateNoAnimationModel = SettingsField(
        default_factory=ValidateNoAnimationModel,
        title="Validate No Animation",
    )
    ValidateNoNamespace: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate No Namespace",
    )
    ValidateNoNullTransforms: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate No Null Transforms",
    )
    ValidateNoUnknownNodes: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate No Unknown Nodes",
    )
    ValidateNodeNoGhosting: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Node No Ghosting",
    )
    ValidateShapeDefaultNames: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Shape Default Names",
    )
    ValidateShapeRenderStats: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Shape Render Stats",
    )
    ValidateShapeZero: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Shape Zero",
    )
    ValidateTransformZero: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Transform Zero",
    )
    ValidateUniqueNames: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Unique Names",
    )
    ValidateNoVRayMesh: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate No V-Ray Proxies (VRayMesh)",
    )
    ValidateUnrealMeshTriangulated: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate if Mesh is Triangulated",
    )
    ValidateAlembicVisibleOnly: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Alembic Visible Node",
    )
    ValidateAlembicDefaultsPointcache: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Alembic Defaults Pointcache"
    )
    ValidateAlembicDefaultsAnimation: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Alembic Defaults Animation"
    )
    ExtractProxyAlembic: ExtractProxyAlembicModel = SettingsField(
        default_factory=ExtractProxyAlembicModel,
        title="Extract Proxy Alembic",
        section="Model Extractors",
    )
    ExtractObj: ExtractObjModel = SettingsField(
        default_factory=ExtractObjModel,
        title="Extract OBJ"
    )
    # Model - END

    # Rig - START
    ValidateRigContents: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Rig Contents",
        section="Rig",
    )
    ValidateRigJointsHidden: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Rig Joints Hidden",
    )
    ValidateRigControllers: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Rig Controllers",
    )
    ValidateAnimationContent: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Animation Content",
    )
    ValidateOutRelatedNodeIds: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Animation Out Set Related Node Ids",
    )
    ValidateRigControllersArnoldAttributes: BasicValidateModel = (
        SettingsField(
            default_factory=BasicValidateModel,
            title="Validate Rig Controllers (Arnold Attributes)",
        )
    )
    ValidateSkeletalMeshHierarchy: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Skeletal Mesh Top Node",
    )
    ValidateSkeletonRigContents: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Skeleton Rig Contents"
    )
    ValidateSkeletonRigControllers: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Skeleton Rig Controllers"
    )
    ValidateSkinclusterDeformerSet: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Skincluster Deformer Relationships",
    )
    ValidateSkeletonRigOutputIds: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Skeleton Rig Output Ids"
    )
    ValidateSkeletonTopGroupHierarchy: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Skeleton Top Group Hierarchy",
    )
    ValidateRigOutSetNodeIds: ValidateRigOutSetNodeIdsModel = SettingsField(
        default_factory=ValidateRigOutSetNodeIdsModel,
        title="Validate Rig Out Set Node Ids",
    )
    ValidateSkeletonRigOutSetNodeIds: ValidateRigOutSetNodeIdsModel = (
        SettingsField(
            default_factory=ValidateRigOutSetNodeIdsModel,
            title="Validate Skeleton Rig Out Set Node Ids",
        )
    )
    # Rig - END
    ValidateCameraAttributes: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Camera Attributes"
    )
    ValidateAssemblyName: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Assembly Name"
    )
    ValidateAssemblyNamespaces: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Assembly Namespaces"
    )
    ValidateAssemblyModelTransforms: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Assembly Model Transforms"
    )
    ValidateAssRelativePaths: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Ass Relative Paths"
    )
    ValidateNoDefaultCameras: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate No Default Cameras"
    )
    ValidateUnrealUpAxis: BasicValidateModel = SettingsField(
        default_factory=BasicValidateModel,
        title="Validate Unreal Up-Axis Check"
    )
    ValidateCameraContents: ValidateCameraContentsModel = SettingsField(
        default_factory=ValidateCameraContentsModel,
        title="Validate Camera Content"
    )
    ExtractPlayblast: ExtractPlayblastSetting = SettingsField(
        default_factory=ExtractPlayblastSetting,
        title="Extract Playblast Settings",
        section="Extractors"
    )
    ExtractMayaSceneRaw: ExtractMayaSceneRawModel = SettingsField(
        default_factory=ExtractMayaSceneRawModel,
        title="Maya Scene(Raw)"
    )
    ExtractCameraAlembic: ExtractCameraAlembicModel = SettingsField(
        default_factory=ExtractCameraAlembicModel,
        title="Extract Camera Alembic"
    )
    ExtractGLB: ExtractGLBModel = SettingsField(
        default_factory=ExtractGLBModel,
        title="Extract GLB"
    )
    ExtractLook: ExtractLookModel = SettingsField(
        default_factory=ExtractLookModel,
        title="Extract Look"
    )
    ExtractGPUCache: ExtractGPUCacheModel = SettingsField(
        default_factory=ExtractGPUCacheModel,
        title="Extract GPU Cache",
    )
    ExtractModel: ExtractModelModel = SettingsField(
        default_factory=ExtractModelModel,
        title="Extract Model (Maya Scene)"
    )
    ExtractAlembic: ExtractAlembicModel = SettingsField(
        default_factory=ExtractAlembicModel,
        title="Extract Alembic"
    )


DEFAULT_SUFFIX_NAMING = {
    "mesh": ["_GEO", "_GES", "_GEP", "_OSD"],
    "nurbsCurve": ["_CRV"],
    "nurbsSurface": ["_NRB"],
    "locator": ["_LOC"],
    "group": ["_GRP"]
}

DEFAULT_PUBLISH_SETTINGS = {
    "CollectMayaRender": {
        "sync_workfile_version": False
    },
    "CollectFbxAnimation": {
        "enabled": False
    },
    "CollectFbxCamera": {
        "enabled": False
    },
    "CollectGLTF": {
        "enabled": False
    },
    "ValidateInstanceInContext": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ValidateFrameRange": {
        "enabled": True,
        "optional": True,
        "active": True,
        "exclude_product_types": [
            "model",
            "rig",
            "staticMesh"
        ]
    },
    "ValidateShaderName": {
        "enabled": False,
        "optional": True,
        "active": True,
        "regex": "(?P<asset>.*)_(.*)_SHD"
    },
    "ValidateShadingEngine": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ValidateMayaColorSpace": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ValidateAttributes": {
        "enabled": False,
        "attributes": "{}"
    },
    "ValidateLoadedPlugin": {
        "enabled": False,
        "optional": True,
        "whitelist_native_plugins": False,
        "authorized_plugins": []
    },
    "ValidateMayaUnits": {
        "enabled": True,
        "optional": False,
        "validate_linear_units": True,
        "linear_units": "cm",
        "validate_angular_units": True,
        "angular_units": "deg",
        "validate_fps": True
    },
    "ValidateUnrealStaticMeshName": {
        "enabled": True,
        "optional": True,
        "validate_mesh": False,
        "validate_collision": True
    },
    "ValidateCycleError": {
        "enabled": True,
        "optional": False,
        "families": [
            "rig"
        ]
    },
    "ValidatePluginPathAttributes": {
        "enabled": False,
        "optional": False,
        "active": True,
        "attribute": [
            {"name": "AlembicNode", "value": "abc_File"},
            {"name": "VRayProxy", "value": "fileName"},
            {"name": "RenderManArchive", "value": "filename"},
            {"name": "pgYetiMaya", "value": "cacheFileName"},
            {"name": "aiStandIn", "value": "dso"},
            {"name": "RedshiftSprite", "value": "tex0"},
            {"name": "RedshiftBokeh", "value": "dofBokehImage"},
            {"name": "RedshiftCameraMap", "value": "tex0"},
            {"name": "RedshiftEnvironment", "value": "tex2"},
            {"name": "RedshiftDomeLight", "value": "tex1"},
            {"name": "RedshiftIESLight", "value": "profile"},
            {"name": "RedshiftLightGobo", "value": "tex0"},
            {"name": "RedshiftNormalMap", "value": "tex0"},
            {"name": "RedshiftProxyMesh", "value": "fileName"},
            {"name": "RedshiftVolumeShape", "value": "fileName"},
            {"name": "VRayTexGLSL", "value": "fileName"},
            {"name": "VRayMtlGLSL", "value": "fileName"},
            {"name": "VRayVRmatMtl", "value": "fileName"},
            {"name": "VRayPtex", "value": "ptexFile"},
            {"name": "VRayLightIESShape", "value": "iesFile"},
            {"name": "VRayMesh", "value": "materialAssignmentsFile"},
            {"name": "VRayMtlOSL", "value": "fileName"},
            {"name": "VRayTexOSL", "value": "fileName"},
            {"name": "VRayTexOCIO", "value": "ocioConfigFile"},
            {"name": "VRaySettingsNode", "value": "pmap_autoSaveFile2"},
            {"name": "VRayScannedMtl", "value": "file"},
            {"name": "VRayScene", "value": "parameterOverrideFilePath"},
            {"name": "VRayMtlMDL", "value": "filename"},
            {"name": "VRaySimbiont", "value": "file"},
            {"name": "dlOpenVDBShape", "value": "filename"},
            {"name": "pgYetiMayaShape", "value": "liveABCFilename"},
            {"name": "gpuCache", "value": "cacheFileName"},
        ]
    },
    "ValidateRenderSettings": {
        "enabled": True,
        "active": True,
        "optional": False,
        "arnold_render_attributes": [],
        "vray_render_attributes": [],
        "redshift_render_attributes": [],
        "renderman_render_attributes": []
    },
    "ValidateResolution": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ValidateCurrentRenderLayerIsRenderable": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateGLSLMaterial": {
        "enabled": False,
        "optional": False,
        "active": True
    },
    "ValidateGLSLPlugin": {
        "enabled": False,
        "optional": False,
        "active": True
    },
    "ValidateRenderImageRule": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateRenderNoDefaultCameras": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateRenderSingleCamera": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateRenderLayerAOVs": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateStepSize": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateVRayDistributedRendering": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateVrayReferencedAOVs": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateVRayTranslatorEnabled": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateVrayProxy": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateVrayProxyMembers": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateYetiRenderScriptCallbacks": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateYetiRigCacheState": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateYetiRigInputShapesInInstance": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateYetiRigSettings": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateModelName": {
        "enabled": False,
        "database": True,
        "material_file": {
            "windows": "",
            "darwin": "",
            "linux": ""
        },
        "regex": "(.*)_(\\d)*_(?P<shader>.*)_(GEO)",
        "top_level_regex": ".*_GRP"
    },
    "ValidateModelContent": {
        "enabled": True,
        "optional": False,
        "validate_top_group": True
    },
    "ValidateTransformNamingSuffix": {
        "enabled": True,
        "optional": True,
        "SUFFIX_NAMING_TABLE": json.dumps(DEFAULT_SUFFIX_NAMING, indent=4),
        "ALLOW_IF_NOT_IN_SUFFIX_TABLE": True
    },
    "ValidateColorSets": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ValidateMeshHasOverlappingUVs": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateMeshArnoldAttributes": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateMeshShaderConnections": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ValidateMeshSingleUVSet": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateMeshHasUVs": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ValidateMeshLaminaFaces": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateMeshNgons": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateMeshNonManifold": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateMeshNoNegativeScale": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateMeshNonZeroEdgeLength": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ValidateMeshNormalsUnlocked": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateMeshUVSetMap1": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateMeshVerticesHaveEdges": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ValidateNoAnimation": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateNoNamespace": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateNoNullTransforms": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateNoUnknownNodes": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateNodeNoGhosting": {
        "enabled": False,
        "optional": False,
        "active": True
    },
    "ValidateShapeDefaultNames": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateShapeRenderStats": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateShapeZero": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateTransformZero": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateUniqueNames": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateNoVRayMesh": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateUnrealMeshTriangulated": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateAlembicVisibleOnly": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ExtractProxyAlembic": {
        "enabled": False,
        "families": [
            "proxyAbc"
        ]
    },
    "ExtractObj": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateRigContents": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateRigJointsHidden": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateRigControllers": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateAnimationContent": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateOutRelatedNodeIds": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateRigControllersArnoldAttributes": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateSkeletalMeshHierarchy": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateSkeletonRigContents": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ValidateSkeletonRigControllers": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateSkinclusterDeformerSet": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateRigOutSetNodeIds": {
        "enabled": True,
        "optional": False,
        "allow_history_only": False
    },
    "ValidateSkeletonRigOutSetNodeIds": {
        "enabled": False,
        "optional": False,
        "allow_history_only": False
    },
    "ValidateSkeletonRigOutputIds": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateSkeletonTopGroupHierarchy": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ValidateCameraAttributes": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateAssemblyName": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ValidateAssemblyNamespaces": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateAssemblyModelTransforms": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateAssRelativePaths": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateNoDefaultCameras": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateUnrealUpAxis": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateCameraContents": {
        "enabled": True,
        "optional": False,
        "validate_shapes": True
    },
    "ValidateAlembicDefaultsPointcache": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ValidateAlembicDefaultsAnimation": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ExtractPlayblast": DEFAULT_PLAYBLAST_SETTING,
    "ExtractMayaSceneRaw": {
        "enabled": True,
        "add_for_families": [
            "layout"
        ]
    },
    "ExtractCameraAlembic": {
        "enabled": True,
        "optional": True,
        "active": True,
        "bake_attributes": "[]"
    },
    "ExtractGLB": {
        "enabled": False,
        "active": True,
        "ogsfx_path": "/maya2glTF/PBR/shaders/glTF_PBR.ogsfx"
    },
    "ExtractLook": {
        "maketx_arguments": []
    },
    "ExtractGPUCache": {
        "enabled": False,
        "optional": False,
        "active": True,
        "families": [
            "model",
            "animation",
            "pointcache"
        ],
        "step": 1.0,
        "stepSave": 1,
        "optimize": True,
        "optimizationThreshold": 40000,
        "optimizeAnimationsForMotionBlur": True,
        "writeMaterials": True,
        "useBaseTessellation": True
    },
    "ExtractModel": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ExtractAlembic": {
        "enabled": True,
        "families": [
            "pointcache",
            "model",
            "vrayproxy.alembic"
        ],
        "attr": "",
        "attrPrefix": "",
        "bake_attributes": [],
        "bake_attribute_prefixes": [],
        "dataFormat": "ogawa",
        "eulerFilter": False,
        "melPerFrameCallback": "",
        "melPostJobCallback": "",
        "overrides": [
            "attr",
            "attrPrefix",
            "renderableOnly",
            "visibleOnly",
            "worldSpace",
            "writeColorSets",
            "writeFaceSets",
            "writeNormals"
        ],
        "preRoll": False,
        "preRollStartFrame": 0,
        "pythonPerFrameCallback": "",
        "pythonPostJobCallback": "",
        "renderableOnly": False,
        "stripNamespaces": True,
        "uvsOnly": False,
        "uvWrite": True,
        "userAttr": "",
        "userAttrPrefix": "",
        "verbose": False,
        "visibleOnly": False,
        "wholeFrameGeo": False,
        "worldSpace": True,
        "writeColorSets": False,
        "writeCreases": False,
        "writeFaceSets": False,
        "writeNormals": True,
        "writeUVSets": False,
        "writeVisibility": False
    }
}
