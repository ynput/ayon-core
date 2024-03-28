from pydantic import validator
from ayon_server.settings import (
    BaseSettingsModel,
    SettingsField,
    ensure_unique_names,
)

from .imageio import ResolveImageIOModel


class CreateShotClipModels(BaseSettingsModel):
    hierarchy: str = SettingsField(
        "{folder}/{sequence}",
        title="Shot parent hierarchy",
        section="Shot Hierarchy And Rename Settings"
    )
    clipRename: bool = SettingsField(
        True,
        title="Rename clips"
    )
    clipName: str = SettingsField(
        "{track}{sequence}{shot}",
        title="Clip name template"
    )
    countFrom: int = SettingsField(
        10,
        title="Count sequence from"
    )
    countSteps: int = SettingsField(
        10,
        title="Stepping number"
    )

    folder: str = SettingsField(
        "shots",
        title="{folder}",
        section="Shot Template Keywords"
    )
    episode: str = SettingsField(
        "ep01",
        title="{episode}"
    )
    sequence: str = SettingsField(
        "sq01",
        title="{sequence}"
    )
    track: str = SettingsField(
        "{_track_}",
        title="{track}"
    )
    shot: str = SettingsField(
        "sh###",
        title="{shot}"
    )

    vSyncOn: bool = SettingsField(
        False,
        title="Enable Vertical Sync",
        section="Vertical Synchronization Of Attributes"
    )

    workfileFrameStart: int = SettingsField(
        1001,
        title="Workfile Start Frame",
        section="Shot Attributes"
    )
    handleStart: int = SettingsField(
        10,
        title="Handle start (head)"
    )
    handleEnd: int = SettingsField(
        10,
        title="Handle end (tail)"
    )


class CreatorPluginsModel(BaseSettingsModel):
    CreateShotClip: CreateShotClipModels = SettingsField(
        default_factory=CreateShotClipModels,
        title="Create Shot Clip"
    )


class MetadataMappingModel(BaseSettingsModel):
    """Metadata mapping

    Representation document context data are used for formatting of
    anatomy tokens. Following are supported:
    - version
    - task
    - asset

    """
    name: str = SettingsField(
        "",
        title="Metadata property name"
    )
    value: str = SettingsField(
        "",
        title="Metadata value template"
    )


class LoadMediaModel(BaseSettingsModel):
    clip_color_last: str = SettingsField(
        "Olive",
        title="Clip color for last version"
    )
    clip_color_old: str = SettingsField(
        "Orange",
        title="Clip color for old version"
    )
    media_pool_bin_path: str = SettingsField(
        "Loader/{folder[path]}",
        title="Media Pool bin path template"
    )
    metadata: list[MetadataMappingModel] = SettingsField(
        default_factory=list,
        title="Metadata mapping",
        description=(
            "Set these media pool item metadata values on load and update. The"
            " keys must match the exact Resolve metadata names like"
            " 'Clip Name' or 'Shot'"
        )
    )

    @validator("metadata")
    def validate_unique_outputs(cls, value):
        ensure_unique_names(value)
        return value


class LoaderPluginsModel(BaseSettingsModel):
    LoadMedia: LoadMediaModel = SettingsField(
        default_factory=LoadMediaModel,
        title="Load Media"
    )


class ResolveSettings(BaseSettingsModel):
    launch_openpype_menu_on_start: bool = SettingsField(
        False, title="Launch OpenPype menu on start of Resolve"
    )
    imageio: ResolveImageIOModel = SettingsField(
        default_factory=ResolveImageIOModel,
        title="Color Management (ImageIO)"
    )
    create: CreatorPluginsModel = SettingsField(
        default_factory=CreatorPluginsModel,
        title="Creator plugins",
    )
    load: LoaderPluginsModel = SettingsField(
        default_factory=LoaderPluginsModel,
        title="Loader plugins",
    )


DEFAULT_VALUES = {
    "launch_openpype_menu_on_start": False,
    "create": {
        "CreateShotClip": {
            "hierarchy": "{folder}/{sequence}",
            "clipRename": True,
            "clipName": "{track}{sequence}{shot}",
            "countFrom": 10,
            "countSteps": 10,
            "folder": "shots",
            "episode": "ep01",
            "sequence": "sq01",
            "track": "{_track_}",
            "shot": "sh###",
            "vSyncOn": False,
            "workfileFrameStart": 1001,
            "handleStart": 10,
            "handleEnd": 10
        }
    },
    "load": {
        "LoadMedia": {
            "clip_color_last": "Olive",
            "clip_color_old": "Orange",
            "media_pool_bin_path": (
                "Loader/{folder[path]}"
            ),
            "metadata": [
                {
                    "name": "Comments",
                    "value": "{version[attrib][comment]}"
                },
                {
                    "name": "Shot",
                    "value": "{folder[path]}"
                },
                {
                    "name": "Take",
                    "value": "{product[name]} {version[name]}"
                },
                {
                    "name": "Clip Name",
                    "value": (
                        "{folder[path]} {product[name]} "
                        "{version[name]} ({representation[name]})"
                    )
                }
            ]
        }
    }
}
