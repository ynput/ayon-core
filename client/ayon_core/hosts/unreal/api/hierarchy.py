import os

from ayon_api import get_folders_hierarchy
from ayon_core.settings import get_project_settings
from ayon_core.hosts.unreal.api.pipeline import (
    generate_sequence,
    set_sequence_hierarchy,
)

import unreal


def get_default_sequence_path(settings):
    """Get default render folder from blender settings."""

    sequence_path = settings['unreal']['sequence_path']
    sequence_path = sequence_path.rstrip("/")

    return f"/Game/{sequence_path}"


def _create_level(path, name, master_level):
    # Create the level
    level_path = f"{path}/{name}_map"
    level_package = f"{level_path}.{name}_map"
    unreal.EditorLevelLibrary.new_level(level_path)

    # Add the level to the master level as sublevel
    unreal.EditorLevelLibrary.load_level(master_level)
    unreal.EditorLevelUtils.add_level_to_world(
        unreal.EditorLevelLibrary.get_editor_world(),
        level_package,
        unreal.LevelStreamingDynamic
    )
    unreal.EditorLevelLibrary.save_all_dirty_levels()

    return level_package


def _create_sequence(
    element, sequence_path, master_level,
    parent_path="", parent_sequence=None, parent_frame_range=None
):
    name = element["name"]
    path = f"{parent_path}/{name}"
    hierarchy_dir = f"{sequence_path}{path}"
    children = element["children"]

    levels = []
    if not children:
        level = _create_level(hierarchy_dir, name, master_level)
        levels.append(level)

    # Create sequence for the current element
    sequence, frame_range = generate_sequence(name, hierarchy_dir)

    # Add the sequence to the parent element if provided
    if parent_sequence:
        set_sequence_hierarchy(
            parent_sequence, sequence,
            parent_frame_range[1],
            frame_range[0], frame_range[1],
            levels)

    if children:
        # Traverse the children and create sequences recursively
        for child in children:
            _create_sequence(
                child, sequence_path, master_level, parent_path=path,
                parent_sequence=sequence, parent_frame_range=frame_range)


def build_sequence_hierarchy():
    """
    Builds the sequence hierarchy by creating sequences from the root element.

    Raises:
        ValueError: If the sequence root element is not found in the hierarchy.
    """
    print("Building sequence hierarchy...")

    project = os.environ.get("AVALON_PROJECT")

    settings = get_project_settings(project)
    sequence_path = get_default_sequence_path(settings)

    sequence_root_name = "shots"

    hierarchy = get_folders_hierarchy(project_name=project)["hierarchy"]

    # Find the sequence root element in the hierarchy
    sequence_root = next((
        element
        for element in hierarchy
        if element["name"] == sequence_root_name
    ), None)

    # Raise an error if the sequence root element is not found
    if not sequence_root:
        raise ValueError(f"Could not find {sequence_root_name} in hierarchy")

    # Create the master level
    master_level_path = (
        f"{sequence_path}/{sequence_root_name}/{sequence_root_name}_map")
    master_level_package = f"{master_level_path}.{sequence_root_name}_map"
    unreal.EditorLevelLibrary.new_level(master_level_path)

    # Start creating sequences from the root element
    _create_sequence(sequence_root, sequence_path, master_level_package)

    # List all the assets in the sequence path and save them
    asset_content = unreal.EditorAssetLibrary.list_assets(
        sequence_path, recursive=True, include_folder=False
    )

    for a in asset_content:
        unreal.EditorAssetLibrary.save_asset(a)

    # Load the master level
    unreal.EditorLevelLibrary.load_level(master_level_package)
