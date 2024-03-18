"""
resolve api
"""
from .utils import (
    get_resolve_module
)

from .pipeline import (
    ResolveHost,
    ls,
    containerise,
    update_container,
    maintained_selection,
)

from .lib import (
    maintain_current_timeline,
    get_project_manager,
    get_current_resolve_project,
    get_current_project, # backward compatibility
    get_current_timeline,
    get_any_timeline,
    get_new_timeline,
    create_bin,
    get_media_pool_item,
    create_media_pool_item,
    create_timeline_item,
    get_timeline_item,
    get_video_track_names,
    get_current_timeline_items,
    get_timeline_item_by_name,
    get_pype_timeline_item_by_name,  # backward compatibility
    get_timeline_item_ayon_tag,
    get_timeline_item_pype_tag,  # backward compatibility
    set_timeline_item_ayon_tag,
    set_timeline_item_pype_tag,  # backward compatibility
    imprint,
    set_publish_attribute,
    get_publish_attribute,
    create_compound_clip,
    swap_clips,
    get_pype_clip_metadata,
    set_project_manager_to_folder_name,
    get_otio_clip_instance_data,
    get_reformated_path
)

from .menu import launch_ayon_menu

from .plugin import (
    ClipLoader,
    TimelineItemLoader,
    ResolveCreator,
    Creator,  # backward compatibility
    PublishableClip,
    PublishClip,  # backward compatibility
)

from .workio import (
    open_file,
    save_file,
    current_file,
    has_unsaved_changes,
    file_extensions,
    work_root
)

from .testing_utils import TestGUI

# Resolve specific singletons
bmdvr = None
bmdvf = None
project_manager = None
media_storage = None


__all__ = [
    "bmdvr",
    "bmdvf",
    "project_manager",
    "media_storage",

    # pipeline
    "ResolveHost",
    "ls",
    "containerise",
    "update_container",
    "maintained_selection",

    # utils
    "get_resolve_module",

    # lib
    "maintain_current_timeline",
    "get_project_manager",
    "get_current_resolve_project",
    "get_current_project", # backward compatibility
    "get_current_timeline",
    "get_any_timeline",
    "get_new_timeline",
    "create_bin",
    "get_media_pool_item",
    "create_media_pool_item",
    "create_timeline_item",
    "get_timeline_item",
    "get_video_track_names",
    "get_current_timeline_items",
    "get_timeline_item_by_name",
    "get_pype_timeline_item_by_name",  # backward compatibility
    "get_timeline_item_ayon_tag",
    "get_timeline_item_pype_tag",  # backward compatibility
    "set_timeline_item_ayon_tag",
    "set_timeline_item_pype_tag",  # backward compatibility
    "imprint",
    "set_publish_attribute",
    "get_publish_attribute",
    "create_compound_clip",
    "swap_clips",
    "get_pype_clip_metadata",
    "set_project_manager_to_folder_name",
    "get_otio_clip_instance_data",
    "get_reformated_path",

    # menu
    "launch_ayon_menu",

    # plugin
    "ClipLoader",
    "TimelineItemLoader",
    "ResolveCreator",
    "Creator",  # backward compatibility
    "PublishableClip",
    "PublishClip",  # backward compatibility

    # workio
    "open_file",
    "save_file",
    "current_file",
    "has_unsaved_changes",
    "file_extensions",
    "work_root",

    "TestGUI"
]
