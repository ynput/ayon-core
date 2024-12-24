from pydantic import validator

from ayon_server.settings import (
    BaseSettingsModel,
    SettingsField,
    MultiplatformPathModel,
    normalize_name,
    ensure_unique_names,
    task_types_enum,
)

from ayon_server.types import ColorRGBA_uint8


class ValidateBaseModel(BaseSettingsModel):
    _isGroup = True
    enabled: bool = SettingsField(True)
    optional: bool = SettingsField(True, title="Optional")
    active: bool = SettingsField(True, title="Active")


class CollectAnatomyInstanceDataModel(BaseSettingsModel):
    _isGroup = True
    follow_workfile_version: bool = SettingsField(
        True, title="Follow workfile version"
    )


class CollectAudioModel(BaseSettingsModel):
    _isGroup = True
    enabled: bool = SettingsField(True)
    audio_product_name: str = SettingsField(
        "", title="Name of audio variant"
    )


class CollectSceneVersionModel(BaseSettingsModel):
    _isGroup = True
    hosts: list[str] = SettingsField(
        default_factory=list,
        title="Host names"
    )
    skip_hosts_headless_publish: list[str] = SettingsField(
        default_factory=list,
        title="Skip for host if headless publish"
    )


class CollectCommentPIModel(BaseSettingsModel):
    enabled: bool = SettingsField(True)
    families: list[str] = SettingsField(default_factory=list, title="Families")


class CollectFramesFixDefModel(BaseSettingsModel):
    enabled: bool = SettingsField(True)
    rewrite_version_enable: bool = SettingsField(
        True,
        title="Show 'Rewrite latest version' toggle"
    )


class ContributionLayersModel(BaseSettingsModel):
    _layout = "compact"
    name: str = SettingsField(title="Name")
    order: str = SettingsField(
        title="Order",
        description="Higher order means a higher strength and stacks the "
                    "layer on top.")


class CollectUSDLayerContributionsModel(BaseSettingsModel):
    enabled: bool = SettingsField(True, title="Enabled")
    contribution_layers: list[ContributionLayersModel] = SettingsField(
        title="Department Layer Orders",
        description=(
            "Define available department layers and their strength "
            "ordering inside the USD contribution workflow."
        )
    )

    @validator("contribution_layers")
    def validate_unique_outputs(cls, value):
        ensure_unique_names(value)
        return value


class AyonEntityURIModel(BaseSettingsModel):
    use_ayon_entity_uri: bool = SettingsField(
        title="Use AYON Entity URI",
        description=(
            "When enabled the USD paths written using the contribution "
            "workflow will use ayon entity URIs instead of resolved published "
            "paths. You can only load these if you use the AYON USD Resolver."
        )
    )


class PluginStateByHostModelProfile(BaseSettingsModel):
    _layout = "expanded"
    # Filtering
    host_names: list[str] = SettingsField(
        default_factory=list,
        title="Host names"
    )
    # Profile values
    enabled: bool = SettingsField(True, title="Enabled")
    optional: bool = SettingsField(True, title="Optional")
    active: bool = SettingsField(True, title="Active")


class PluginStateByHostModel(BaseSettingsModel):
    _isGroup = True
    plugin_state_profiles: list[PluginStateByHostModelProfile] = SettingsField(
        default_factory=list,
        title="Plugin enable state profiles",
        description="Change plugin state based on host name."
    )


class ValidateIntentProfile(BaseSettingsModel):
    _layout = "expanded"
    hosts: list[str] = SettingsField(default_factory=list, title="Host names")
    task_types: list[str] = SettingsField(
        default_factory=list,
        title="Task types",
        enum_resolver=task_types_enum
    )
    tasks: list[str] = SettingsField(default_factory=list, title="Task names")
    # TODO This was 'validate' in v3
    validate_intent: bool = SettingsField(True, title="Validate")


class ValidateIntentModel(BaseSettingsModel):
    """Validate if Publishing intent was selected.

    It is possible to disable validation for specific publishing context
    with profiles.
    """

    _isGroup = True
    enabled: bool = SettingsField(False)
    profiles: list[ValidateIntentProfile] = SettingsField(default_factory=list)


class ExtractThumbnailFFmpegModel(BaseSettingsModel):
    input: list[str] = SettingsField(
        default_factory=list,
        title="FFmpeg input arguments"
    )
    output: list[str] = SettingsField(
        default_factory=list,
        title="FFmpeg input arguments"
    )


class ResizeItemModel(BaseSettingsModel):
    _layout = "expanded"
    width: int = SettingsField(
        1920,
        ge=0,
        le=100000,
        title="Width",
        description="Width and Height must be both set to higher value than 0"
        " else source resolution is used."
    )
    height: int = SettingsField(
        1080,
        title="Height",
        ge=0,
        le=100000,
    )


_resize_types_enum = [
    {"value": "source", "label": "Image source"},
    {"value": "resize", "label": "Resize"},
]


class ResizeModel(BaseSettingsModel):
    _layout = "expanded"

    type: str = SettingsField(
        title="Type",
        description="Type of resizing",
        enum_resolver=lambda: _resize_types_enum,
        conditionalEnum=True,
        default="source"
    )

    resize: ResizeItemModel = SettingsField(
        default_factory=ResizeItemModel,
        title="Resize"
    )


_thumbnail_oiio_transcoding_type = [
    {"value": "colorspace", "label": "Use Colorspace"},
    {"value": "display_and_view", "label": "Use Display&View"}
]


class DisplayAndViewModel(BaseSettingsModel):
    _layout = "expanded"
    display: str = SettingsField(
        "default",
        title="Display"
    )
    view: str = SettingsField(
        "sRGB",
        title="View"
    )


class ExtractThumbnailOIIODefaultsModel(BaseSettingsModel):
    type: str = SettingsField(
        title="Type",
        description="Transcoding type",
        enum_resolver=lambda: _thumbnail_oiio_transcoding_type,
        conditionalEnum=True,
        default="colorspace"
    )

    colorspace: str = SettingsField(
        "",
        title="Colorspace"
    )
    display_and_view: DisplayAndViewModel = SettingsField(
        default_factory=DisplayAndViewModel,
        title="Display&View"
    )


class ExtractThumbnailModel(BaseSettingsModel):
    _isGroup = True
    enabled: bool = SettingsField(True)
    product_names: list[str] = SettingsField(
        default_factory=list,
        title="Product names"
    )
    integrate_thumbnail: bool = SettingsField(
        True,
        title="Integrate Thumbnail Representation"
    )
    target_size: ResizeModel = SettingsField(
        default_factory=ResizeModel,
        title="Target size"
    )
    background_color: ColorRGBA_uint8 = SettingsField(
        (0, 0, 0, 0.0),
        title="Background color"
    )
    duration_split: float = SettingsField(
        0.5,
        title="Duration split",
        ge=0.0,
        le=1.0
    )
    oiiotool_defaults: ExtractThumbnailOIIODefaultsModel = SettingsField(
        default_factory=ExtractThumbnailOIIODefaultsModel,
        title="OIIOtool defaults"
    )
    ffmpeg_args: ExtractThumbnailFFmpegModel = SettingsField(
        default_factory=ExtractThumbnailFFmpegModel
    )


def _extract_oiio_transcoding_type():
    return [
        {"value": "colorspace", "label": "Use Colorspace"},
        {"value": "display_view", "label": "Use Display&View"}
    ]


class OIIOToolArgumentsModel(BaseSettingsModel):
    additional_command_args: list[str] = SettingsField(
        default_factory=list,
        title="Arguments",
        description="Additional command line arguments for *oiiotool*."
    )


class UseDisplayViewModel(BaseSettingsModel):
    _layout = "expanded"
    display: str = SettingsField(
        "",
        title="Target Display",
        description=(
            "Display of the target transform. If left empty, the"
            " source Display value will be used."
        )
    )
    view: str = SettingsField(
        "",
        title="Target View",
        description=(
            "View of the target transform. If left empty, the"
            " source View value will be used."
        )
    )


class ExtractOIIOTranscodeOutputModel(BaseSettingsModel):
    _layout = "expanded"
    name: str = SettingsField(
        "",
        title="Name",
        description="Output name (no space)",
        regex=r"[a-zA-Z0-9_]([a-zA-Z0-9_\.\-]*[a-zA-Z0-9_])?$",
    )
    extension: str = SettingsField(
        "",
        title="Extension",
        description=(
            "Target extension. If left empty, original"
            " extension is used."
        ),
    )
    transcoding_type: str = SettingsField(
        "colorspace",
        title="Transcoding type",
        enum_resolver=_extract_oiio_transcoding_type,
        conditionalEnum=True,
        description=(
            "Select the transcoding type for your output, choosing either "
            "*Colorspace* or *Display&View* transform."
            " Only one option can be applied per output definition."
        ),
    )
    colorspace: str = SettingsField(
        "",
        title="Target Colorspace",
        description=(
            "Choose the desired target colorspace, confirming its availability"
            " in the active OCIO config. If left empty, the"
            " source colorspace value will be used, resulting in no"
            " colorspace conversion."
        )
    )
    display_view: UseDisplayViewModel = SettingsField(
        title="Use Display&View",
        default_factory=UseDisplayViewModel
    )

    oiiotool_args: OIIOToolArgumentsModel = SettingsField(
        default_factory=OIIOToolArgumentsModel,
        title="OIIOtool arguments")

    tags: list[str] = SettingsField(
        default_factory=list,
        title="Tags",
        description=(
            "Additional tags that will be added to the created representation."
            "\nAdd *review* tag to create review from the transcoded"
            " representation instead of the original."
        )
    )
    custom_tags: list[str] = SettingsField(
        default_factory=list,
        title="Custom Tags",
        description=(
            "Additional custom tags that will be added"
            " to the created representation."
        )
    )


class ExtractOIIOTranscodeProfileModel(BaseSettingsModel):
    product_types: list[str] = SettingsField(
        default_factory=list,
        title="Product types"
    )
    hosts: list[str] = SettingsField(
        default_factory=list,
        title="Host names"
    )
    task_types: list[str] = SettingsField(
        default_factory=list,
        title="Task types",
        enum_resolver=task_types_enum
    )
    task_names: list[str] = SettingsField(
        default_factory=list,
        title="Task names"
    )
    product_names: list[str] = SettingsField(
        default_factory=list,
        title="Product names"
    )
    delete_original: bool = SettingsField(
        True,
        title="Delete Original Representation",
        description=(
            "Choose to preserve or remove the original representation.\n"
            "Keep in mind that if the transcoded representation includes"
            " a `review` tag, it will take precedence over"
            " the original for creating reviews."
        ),
    )
    outputs: list[ExtractOIIOTranscodeOutputModel] = SettingsField(
        default_factory=list,
        title="Output Definitions",
    )

    @validator("outputs")
    def validate_unique_outputs(cls, value):
        ensure_unique_names(value)
        return value


class ExtractOIIOTranscodeModel(BaseSettingsModel):
    enabled: bool = SettingsField(True)
    profiles: list[ExtractOIIOTranscodeProfileModel] = SettingsField(
        default_factory=list, title="Profiles"
    )


# --- [START] Extract Review ---
class ExtractReviewFFmpegModel(BaseSettingsModel):
    video_filters: list[str] = SettingsField(
        default_factory=list,
        title="Video filters"
    )
    audio_filters: list[str] = SettingsField(
        default_factory=list,
        title="Audio filters"
    )
    input: list[str] = SettingsField(
        default_factory=list,
        title="Input arguments"
    )
    output: list[str] = SettingsField(
        default_factory=list,
        title="Output arguments"
    )


def extract_review_filter_enum():
    return [
        {
            "value": "everytime",  # codespell:ignore everytime
            "label": "Always"
        },
        {
            "value": "single_frame",
            "label": "Only if input has 1 image frame"
        },
        {
            "value": "multi_frame",
            "label": "Only if input is video or sequence of frames"
        }
    ]


class ExtractReviewFilterModel(BaseSettingsModel):
    families: list[str] = SettingsField(default_factory=list, title="Families")
    product_names: list[str] = SettingsField(
        default_factory=list, title="Product names")
    custom_tags: list[str] = SettingsField(
        default_factory=list, title="Custom Tags"
    )
    single_frame_filter: str = SettingsField(
        "everytime",  # codespell:ignore everytime
        description=(
            "Use output **always** / only if input **is 1 frame**"
            " image / only if has **2+ frames** or **is video**"
        ),
        enum_resolver=extract_review_filter_enum
    )


class ExtractReviewLetterBox(BaseSettingsModel):
    enabled: bool = SettingsField(True)
    ratio: float = SettingsField(
        0.0,
        title="Ratio",
        ge=0.0,
        le=10000.0
    )
    fill_color: ColorRGBA_uint8 = SettingsField(
        (0, 0, 0, 0.0),
        title="Fill Color"
    )
    line_thickness: int = SettingsField(
        0,
        title="Line Thickness",
        ge=0,
        le=1000
    )
    line_color: ColorRGBA_uint8 = SettingsField(
        (0, 0, 0, 0.0),
        title="Line Color"
    )


class ExtractReviewOutputDefModel(BaseSettingsModel):
    _layout = "expanded"
    name: str = SettingsField("", title="Name")
    ext: str = SettingsField("", title="Output extension")
    # TODO use some different source of tags
    tags: list[str] = SettingsField(default_factory=list, title="Tags")
    burnins: list[str] = SettingsField(
        default_factory=list, title="Link to a burnin by name"
    )
    ffmpeg_args: ExtractReviewFFmpegModel = SettingsField(
        default_factory=ExtractReviewFFmpegModel,
        title="FFmpeg arguments"
    )
    filter: ExtractReviewFilterModel = SettingsField(
        default_factory=ExtractReviewFilterModel,
        title="Additional output filtering"
    )
    overscan_crop: str = SettingsField(
        "",
        title="Overscan crop",
        description=(
            "Crop input overscan. See the documentation for more information."
        )
    )
    overscan_color: ColorRGBA_uint8 = SettingsField(
        (0, 0, 0, 0.0),
        title="Overscan color",
        description=(
            "Overscan color is used when input aspect ratio is not"
            " same as output aspect ratio."
        )
    )
    # overscan_color: ColorRGB_uint8 = SettingsField(
    #     (0, 0, 0),
    #     title="Overscan color",
    #     description=(
    #         "Overscan color is used when input aspect ratio is not"
    #         " same as output aspect ratio."
    #     )
    # )
    width: int = SettingsField(
        0,
        ge=0,
        le=100000,
        title="Output width",
        description=(
            "Width and Height must be both set to higher"
            " value than 0 else source resolution is used."
        )
    )
    height: int = SettingsField(
        0,
        title="Output height",
        ge=0,
        le=100000,
    )
    scale_pixel_aspect: bool = SettingsField(
        True,
        title="Scale pixel aspect",
        description=(
            "Rescale input when it's pixel aspect ratio is not 1."
            " Useful for anamorphic reviews."
        )
    )
    bg_color: ColorRGBA_uint8 = SettingsField(
        (0, 0, 0, 0.0),
        description=(
            "Background color is used only when input have transparency"
            " and Alpha is higher than 0."
        ),
        title="Background color",
    )
    letter_box: ExtractReviewLetterBox = SettingsField(
        default_factory=ExtractReviewLetterBox,
        title="Letter Box"
    )

    @validator("name")
    def validate_name(cls, value):
        """Ensure name does not contain weird characters"""
        return normalize_name(value)


class ExtractReviewProfileModel(BaseSettingsModel):
    _layout = "expanded"
    product_types: list[str] = SettingsField(
        default_factory=list, title="Product types"
    )
    # TODO use hosts enum
    hosts: list[str] = SettingsField(
        default_factory=list, title="Host names"
    )
    outputs: list[ExtractReviewOutputDefModel] = SettingsField(
        default_factory=list, title="Output Definitions"
    )

    @validator("outputs")
    def validate_unique_outputs(cls, value):
        ensure_unique_names(value)
        return value


class ExtractReviewModel(BaseSettingsModel):
    _isGroup = True
    enabled: bool = SettingsField(True)
    profiles: list[ExtractReviewProfileModel] = SettingsField(
        default_factory=list,
        title="Profiles"
    )
# --- [END] Extract Review ---


# --- [Start] Extract Burnin ---
class ExtractBurninOptionsModel(BaseSettingsModel):
    font_size: int = SettingsField(0, ge=0, title="Font size")
    font_color: ColorRGBA_uint8 = SettingsField(
        (255, 255, 255, 1.0),
        title="Font color"
    )
    bg_color: ColorRGBA_uint8 = SettingsField(
        (0, 0, 0, 1.0),
        title="Background color"
    )
    x_offset: int = SettingsField(0, title="X Offset")
    y_offset: int = SettingsField(0, title="Y Offset")
    bg_padding: int = SettingsField(0, title="Padding around text")
    font_filepath: MultiplatformPathModel = SettingsField(
        default_factory=MultiplatformPathModel,
        title="Font file path"
    )


class ExtractBurninDefFilter(BaseSettingsModel):
    families: list[str] = SettingsField(
        default_factory=list,
        title="Families"
    )
    tags: list[str] = SettingsField(
        default_factory=list,
        title="Tags"
    )


class ExtractBurninDef(BaseSettingsModel):
    _isGroup = True
    _layout = "expanded"
    name: str = SettingsField("")
    TOP_LEFT: str = SettingsField("", title="Top Left")
    TOP_CENTERED: str = SettingsField("", title="Top Centered")
    TOP_RIGHT: str = SettingsField("", title="Top Right")
    BOTTOM_LEFT: str = SettingsField("", title="Bottom Left")
    BOTTOM_CENTERED: str = SettingsField("", title="Bottom Centered")
    BOTTOM_RIGHT: str = SettingsField("", title="Bottom Right")
    filter: ExtractBurninDefFilter = SettingsField(
        default_factory=ExtractBurninDefFilter,
        title="Additional filtering"
    )

    @validator("name")
    def validate_name(cls, value):
        """Ensure name does not contain weird characters"""
        return normalize_name(value)


class ExtractBurninProfile(BaseSettingsModel):
    _layout = "expanded"
    product_types: list[str] = SettingsField(
        default_factory=list,
        title="Product types"
    )
    hosts: list[str] = SettingsField(
        default_factory=list,
        title="Host names"
    )
    task_types: list[str] = SettingsField(
        default_factory=list,
        title="Task types",
        enum_resolver=task_types_enum
    )
    task_names: list[str] = SettingsField(
        default_factory=list,
        title="Task names"
    )
    product_names: list[str] = SettingsField(
        default_factory=list,
        title="Product names"
    )
    burnins: list[ExtractBurninDef] = SettingsField(
        default_factory=list,
        title="Burnins"
    )

    @validator("burnins")
    def validate_unique_outputs(cls, value):
        ensure_unique_names(value)

        return value


class ExtractBurninModel(BaseSettingsModel):
    _isGroup = True
    enabled: bool = SettingsField(True)
    options: ExtractBurninOptionsModel = SettingsField(
        default_factory=ExtractBurninOptionsModel,
        title="Burnin formatting options"
    )
    profiles: list[ExtractBurninProfile] = SettingsField(
        default_factory=list,
        title="Profiles"
    )
# --- [END] Extract Burnin ---


class PreIntegrateThumbnailsProfile(BaseSettingsModel):
    _isGroup = True
    product_types: list[str] = SettingsField(
        default_factory=list,
        title="Product types",
    )
    hosts: list[str] = SettingsField(
        default_factory=list,
        title="Hosts",
    )
    task_types: list[str] = SettingsField(
        default_factory=list,
        title="Task types",
        enum_resolver=task_types_enum
    )
    product_names: list[str] = SettingsField(
        default_factory=list,
        title="Product names",
    )
    integrate_thumbnail: bool = SettingsField(True)


class PreIntegrateThumbnailsModel(BaseSettingsModel):
    """Explicitly set if Thumbnail representation should be integrated.

    If no matching profile set, existing state from Host implementation
    is kept.
    """

    _isGroup = True
    enabled: bool = SettingsField(True)
    integrate_profiles: list[PreIntegrateThumbnailsProfile] = SettingsField(
        default_factory=list,
        title="Integrate profiles"
    )


class IntegrateProductGroupProfile(BaseSettingsModel):
    product_types: list[str] = SettingsField(
        default_factory=list,
        title="Product types"
    )
    hosts: list[str] = SettingsField(default_factory=list, title="Hosts")
    task_types: list[str] = SettingsField(
        default_factory=list,
        title="Task types",
        enum_resolver=task_types_enum
    )
    tasks: list[str] = SettingsField(default_factory=list, title="Task names")
    template: str = SettingsField("", title="Template")


class IntegrateProductGroupModel(BaseSettingsModel):
    """Group published products by filtering logic.

    Set all published instances as a part of specific group named according
     to 'Template'.

    Implemented all variants of placeholders '{task}', '{product[type]}',
    '{host}', '{product[name]}', '{renderlayer}'.
    """

    _isGroup = True
    product_grouping_profiles: list[IntegrateProductGroupProfile] = (
        SettingsField(
            default_factory=list,
            title="Product group profiles"
        )
    )


class IntegrateANProductGroupProfileModel(BaseSettingsModel):
    product_types: list[str] = SettingsField(
        default_factory=list,
        title="Product types"
    )
    hosts: list[str] = SettingsField(
        default_factory=list,
        title="Hosts"
    )
    task_types: list[str] = SettingsField(
        default_factory=list,
        title="Task types",
        enum_resolver=task_types_enum
    )
    tasks: list[str] = SettingsField(
        default_factory=list,
        title="Task names"
    )
    template: str = SettingsField("", title="Template")


class IntegrateANTemplateNameProfileModel(BaseSettingsModel):
    product_types: list[str] = SettingsField(
        default_factory=list,
        title="Product types"
    )
    hosts: list[str] = SettingsField(
        default_factory=list,
        title="Hosts"
    )
    task_types: list[str] = SettingsField(
        default_factory=list,
        title="Task types",
        enum_resolver=task_types_enum
    )
    tasks: list[str] = SettingsField(
        default_factory=list,
        title="Task names"
    )
    template_name: str = SettingsField("", title="Template name")


class IntegrateHeroTemplateNameProfileModel(BaseSettingsModel):
    product_types: list[str] = SettingsField(
        default_factory=list,
        title="Product types"
    )
    hosts: list[str] = SettingsField(
        default_factory=list,
        title="Hosts"
    )
    task_types: list[str] = SettingsField(
        default_factory=list,
        title="Task types",
        enum_resolver=task_types_enum
    )
    task_names: list[str] = SettingsField(
        default_factory=list,
        title="Task names"
    )
    template_name: str = SettingsField("", title="Template name")


class IntegrateHeroVersionModel(BaseSettingsModel):
    _isGroup = True
    enabled: bool = SettingsField(True)
    optional: bool = SettingsField(False, title="Optional")
    active: bool = SettingsField(True, title="Active")
    families: list[str] = SettingsField(default_factory=list, title="Families")
    use_hardlinks: bool = SettingsField(
        False, title="Use Hardlinks",
        description="When enabled first try to make a hardlink of the version "
                    "instead of a copy. This helps reduce disk usage, but may "
                    "create issues.\nFor example there are known issues on "
                    "Windows being unable to delete any of the hardlinks if "
                    "any of the links is in use creating issues with updating "
                    "hero versions.")


class CleanUpModel(BaseSettingsModel):
    _isGroup = True
    paterns: list[str] = SettingsField(  # codespell:ignore paterns
        default_factory=list,
        title="Patterns (regex)"
    )
    remove_temp_renders: bool = SettingsField(
        False, title="Remove Temp renders"
    )


class CleanUpFarmModel(BaseSettingsModel):
    _isGroup = True
    enabled: bool = SettingsField(True)


class PublishPuginsModel(BaseSettingsModel):
    CollectAnatomyInstanceData: CollectAnatomyInstanceDataModel = (
        SettingsField(
            default_factory=CollectAnatomyInstanceDataModel,
            title="Collect Anatomy Instance Data"
        )
    )
    CollectAudio: CollectAudioModel = SettingsField(
        default_factory=CollectAudioModel,
        title="Collect Audio"
    )
    CollectSceneVersion: CollectSceneVersionModel = SettingsField(
        default_factory=CollectSceneVersionModel,
        title="Collect Version from Workfile"
    )
    collect_comment_per_instance: CollectCommentPIModel = SettingsField(
        default_factory=CollectCommentPIModel,
        title="Collect comment per instance",
    )
    CollectFramesFixDef: CollectFramesFixDefModel = SettingsField(
        default_factory=CollectFramesFixDefModel,
        title="Collect Frames to Fix",
    )
    CollectUSDLayerContributions: CollectUSDLayerContributionsModel = (
        SettingsField(
            default_factory=CollectUSDLayerContributionsModel,
            title="Collect USD Layer Contributions",
        )
    )
    ValidateEditorialAssetName: ValidateBaseModel = SettingsField(
        default_factory=ValidateBaseModel,
        title="Validate Editorial Asset Name"
    )
    ValidateVersion: PluginStateByHostModel = SettingsField(
        default_factory=PluginStateByHostModel,
        title="Validate Version",
        description=(
            "Validate that product version to integrate"
            " is newer than latest version in AYON."
        )
    )
    ValidateOutdatedContainers: PluginStateByHostModel = SettingsField(
        default_factory=PluginStateByHostModel,
        title="Validate Outdated Containers"
    )
    ValidateIntent: ValidateIntentModel = SettingsField(
        default_factory=ValidateIntentModel,
        title="Validate Intent"
    )
    ExtractThumbnail: ExtractThumbnailModel = SettingsField(
        default_factory=ExtractThumbnailModel,
        title="Extract Thumbnail"
    )
    ExtractOIIOTranscode: ExtractOIIOTranscodeModel = SettingsField(
        default_factory=ExtractOIIOTranscodeModel,
        title="Extract OIIO Transcode"
    )
    ExtractReview: ExtractReviewModel = SettingsField(
        default_factory=ExtractReviewModel,
        title="Extract Review"
    )
    ExtractBurnin: ExtractBurninModel = SettingsField(
        default_factory=ExtractBurninModel,
        title="Extract Burnin"
    )
    ExtractUSDAssetContribution: AyonEntityURIModel = SettingsField(
        default_factory=AyonEntityURIModel,
        title="Extract USD Asset Contribution",
    )
    ExtractUSDLayerContribution: AyonEntityURIModel = SettingsField(
        default_factory=AyonEntityURIModel,
        title="Extract USD Layer Contribution",
    )
    PreIntegrateThumbnails: PreIntegrateThumbnailsModel = SettingsField(
        default_factory=PreIntegrateThumbnailsModel,
        title="Override Integrate Thumbnail Representations"
    )
    IntegrateProductGroup: IntegrateProductGroupModel = SettingsField(
        default_factory=IntegrateProductGroupModel,
        title="Integrate Product Group"
    )
    IntegrateHeroVersion: IntegrateHeroVersionModel = SettingsField(
        default_factory=IntegrateHeroVersionModel,
        title="Integrate Hero Version"
    )
    CleanUp: CleanUpModel = SettingsField(
        default_factory=CleanUpModel,
        title="Clean Up"
    )
    CleanUpFarm: CleanUpFarmModel = SettingsField(
        default_factory=CleanUpFarmModel,
        title="Clean Up Farm"
    )


DEFAULT_PUBLISH_VALUES = {
    "CollectAnatomyInstanceData": {
        "follow_workfile_version": False
    },
    "CollectAudio": {
        "enabled": False,
        "audio_product_name": "audioMain"
    },
    "CollectSceneVersion": {
        "hosts": [
            "aftereffects",
            "blender",
            "celaction",
            "fusion",
            "harmony",
            "hiero",
            "houdini",
            "maya",
            "nuke",
            "photoshop",
            "resolve",
            "tvpaint",
            "substancepainter"
        ],
        "skip_hosts_headless_publish": []
    },
    "collect_comment_per_instance": {
        "enabled": False,
        "families": []
    },
    "CollectFramesFixDef": {
        "enabled": True,
        "rewrite_version_enable": True
    },
    "CollectUSDLayerContributions": {
        "enabled": True,
        "contribution_layers": [
            # Asset layers
            {"name": "model", "order": 100},
            {"name": "assembly", "order": 150},
            {"name": "groom", "order": 175},
            {"name": "look", "order": 300},
            {"name": "rig", "order": 100},
            # Shot layers
            {"name": "layout", "order": 200},
            {"name": "animation", "order": 300},
            {"name": "simulation", "order": 400},
            {"name": "fx", "order": 500},
            {"name": "lighting", "order": 600},
        ],
    },
    "ValidateEditorialAssetName": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateVersion": {
        "plugin_state_profiles": [
            {
                "host_names": [
                    "aftereffects",
                    "blender",
                    "houdini",
                    "maya",
                    "nuke",
                    "photoshop",
                    "substancepainter"
                ],
                "enabled": True,
                "optional": False,
                "active": True
            }
        ]
    },
    "ValidateOutdatedContainers": {
        "plugin_state_profiles": [
            {
                # Default host names are based on original
                #   filter of ValidateContainer pyblish plugin
                "host_names": [
                    "maya",
                    "houdini",
                    "nuke",
                    "harmony",
                    "photoshop",
                    "aftereffects",
                    "fusion"
                ],
                "enabled": True,
                "optional": True,
                "active": True
            }
        ]
    },
    "ValidateIntent": {
        "enabled": False,
        "profiles": []
    },
    "ExtractThumbnail": {
        "enabled": True,
        "product_names": [],
        "integrate_thumbnail": True,
        "target_size": {
            "type": "source"
        },
        "duration_split": 0.5,
        "oiiotool_defaults": {
            "type": "colorspace",
            "colorspace": "color_picking"
        },
        "ffmpeg_args": {
            "input": [
                "-apply_trc gamma22"
            ],
            "output": []
        }
    },
    "ExtractOIIOTranscode": {
        "enabled": True,
        "profiles": []
    },
    "ExtractReview": {
        "enabled": True,
        "profiles": [
            {
                "product_types": [],
                "hosts": [],
                "outputs": [
                    {
                        "name": "png",
                        "ext": "png",
                        "tags": [
                            "ftrackreview",
                            "kitsureview",
                            "webreview"
                        ],
                        "burnins": [],
                        "ffmpeg_args": {
                            "video_filters": [],
                            "audio_filters": [],
                            "input": [],
                            "output": []
                        },
                        "filter": {
                            "families": [
                                "render",
                                "review",
                                "ftrack"
                            ],
                            "product_names": [],
                            "custom_tags": [],
                            "single_frame_filter": "single_frame"
                        },
                        "overscan_crop": "",
                        # "overscan_color": [0, 0, 0],
                        "overscan_color": [0, 0, 0, 0.0],
                        "width": 1920,
                        "height": 1080,
                        "scale_pixel_aspect": True,
                        "bg_color": [0, 0, 0, 0.0],
                        "letter_box": {
                            "enabled": False,
                            "ratio": 0.0,
                            "fill_color": [0, 0, 0, 1.0],
                            "line_thickness": 0,
                            "line_color": [255, 0, 0, 1.0]
                        }
                    },
                    {
                        "name": "h264",
                        "ext": "mp4",
                        "tags": [
                            "burnin",
                            "ftrackreview",
                            "kitsureview",
                            "webreview"
                        ],
                        "burnins": [],
                        "ffmpeg_args": {
                            "video_filters": [],
                            "audio_filters": [],
                            "input": [
                                "-apply_trc gamma22"
                            ],
                            "output": [
                                "-pix_fmt yuv420p",
                                "-crf 18",
                                "-c:a aac",
                                "-b:a 192k",
                                "-g 1",
                                "-movflags faststart"
                            ]
                        },
                        "filter": {
                            "families": [
                                "render",
                                "review",
                                "ftrack"
                            ],
                            "product_names": [],
                            "custom_tags": [],
                            "single_frame_filter": "multi_frame"
                        },
                        "overscan_crop": "",
                        # "overscan_color": [0, 0, 0],
                        "overscan_color": [0, 0, 0, 0.0],
                        "width": 0,
                        "height": 0,
                        "scale_pixel_aspect": True,
                        "bg_color": [0, 0, 0, 0.0],
                        "letter_box": {
                            "enabled": False,
                            "ratio": 0.0,
                            "fill_color": [0, 0, 0, 1.0],
                            "line_thickness": 0,
                            "line_color": [255, 0, 0, 1.0]
                        }
                    }
                ]
            }
        ]
    },
    "ExtractBurnin": {
        "enabled": True,
        "options": {
            "font_size": 42,
            "font_color": [255, 255, 255, 1.0],
            "bg_color": [0, 0, 0, 0.5],
            "x_offset": 5,
            "y_offset": 5,
            "bg_padding": 5,
            "font_filepath": {
                "windows": "",
                "darwin": "",
                "linux": ""
            }
        },
        "profiles": [
            {
                "product_types": [],
                "hosts": [],
                "task_types": [],
                "task_names": [],
                "product_names": [],
                "burnins": [
                    {
                        "name": "burnin",
                        "TOP_LEFT": "{yy}-{mm}-{dd}",
                        "TOP_CENTERED": "",
                        "TOP_RIGHT": "{anatomy[version]}",
                        "BOTTOM_LEFT": "{username}",
                        "BOTTOM_CENTERED": "{folder[name]}",
                        "BOTTOM_RIGHT": (
                            "{frame_start}-{current_frame}-{frame_end}"
                        ),
                        "filter": {
                            "families": [],
                            "tags": []
                        }
                    },
                ]
            },
            {
                "product_types": ["review"],
                "hosts": [
                    "maya",
                    "houdini",
                    "max"
                ],
                "task_types": [],
                "task_names": [],
                "product_names": [],
                "burnins": [
                    {
                        "name": "focal_length_burnin",
                        "TOP_LEFT": "{yy}-{mm}-{dd}",
                        "TOP_CENTERED": "{focalLength:.2f} mm",
                        "TOP_RIGHT": "{anatomy[version]}",
                        "BOTTOM_LEFT": "{username}",
                        "BOTTOM_CENTERED": "{folder[name]}",
                        "BOTTOM_RIGHT": (
                            "{frame_start}-{current_frame}-{frame_end}"
                        ),
                        "filter": {
                            "families": [],
                            "tags": []
                        }
                    }
                ]
            }
        ]
    },
    "ExtractUSDAssetContribution": {
        "use_ayon_entity_uri": False,
    },
    "ExtractUSDLayerContribution": {
        "use_ayon_entity_uri": False,
    },
    "PreIntegrateThumbnails": {
        "enabled": True,
        "integrate_profiles": []
    },
    "IntegrateProductGroup": {
        "product_grouping_profiles": [
            {
                "product_types": [],
                "hosts": [],
                "task_types": [],
                "tasks": [],
                "template": ""
            }
        ]
    },
    "IntegrateHeroVersion": {
        "enabled": True,
        "optional": True,
        "active": True,
        "families": [
            "model",
            "rig",
            "look",
            "pointcache",
            "animation",
            "setdress",
            "layout",
            "mayaScene",
            "simpleUnrealTexture"
        ],
        "use_hardlinks": False
    },
    "CleanUp": {
        "paterns": [],  # codespell:ignore paterns
        "remove_temp_renders": False
    },
    "CleanUpFarm": {
        "enabled": False
    }
}
