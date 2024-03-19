import os
import re
import json
import contextlib
import logging

import ayon_api

from ayon_core.pipeline.context_tools import get_current_context

from .ws_stub import get_stub

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


@contextlib.contextmanager
def maintained_selection():
    """Maintain selection during context."""
    selection = get_stub().get_selected_items(True, False, False)
    try:
        yield selection
    finally:
        pass


def get_extension_manifest_path():
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "extension",
        "CSXS",
        "manifest.xml"
    )


def get_unique_layer_name(layers, name):
    """
        Gets all layer names and if 'name' is present in them, increases
        suffix by 1 (eg. creates unique layer name - for Loader)
    Args:
        layers (list): of strings, names only
        name (string):  checked value

    Returns:
        (string): name_00X (without version)
    """
    names = {}
    for layer in layers:
        layer_name = re.sub(r'_\d{3}$', '', layer)
        if layer_name in names.keys():
            names[layer_name] = names[layer_name] + 1
        else:
            names[layer_name] = 1
    occurrences = names.get(name, 0)

    return "{}_{:0>3d}".format(name, occurrences + 1)


def get_background_layers(file_url):
    """
        Pulls file name from background json file, enrich with folder url for
        AE to be able import files.

        Order is important, follows order in json.

        Args:
            file_url (str): abs url of background json

        Returns:
            (list): of abs paths to images
    """
    with open(file_url) as json_file:
        data = json.load(json_file)

    layers = list()
    bg_folder = os.path.dirname(file_url)
    for child in data['children']:
        if child.get("filename"):
            layers.append(os.path.join(bg_folder, child.get("filename")).
                          replace("\\", "/"))
        else:
            for layer in child['children']:
                if layer.get("filename"):
                    layers.append(os.path.join(bg_folder,
                                               layer.get("filename")).
                                  replace("\\", "/"))
    return layers


def get_folder_settings(folder_entity):
    """Get settings of current folder.

    Returns:
        dict: Scene data.

    """
    folder_attributes = folder_entity["attrib"]
    fps = folder_attributes.get("fps", 0)
    frame_start = folder_attributes.get("frameStart", 0)
    frame_end = folder_attributes.get("frameEnd", 0)
    handle_start = folder_attributes.get("handleStart", 0)
    handle_end = folder_attributes.get("handleEnd", 0)
    resolution_width = folder_attributes.get("resolutionWidth", 0)
    resolution_height = folder_attributes.get("resolutionHeight", 0)
    duration = (frame_end - frame_start + 1) + handle_start + handle_end

    return {
        "fps": fps,
        "frameStart": frame_start,
        "frameEnd": frame_end,
        "handleStart": handle_start,
        "handleEnd": handle_end,
        "resolutionWidth": resolution_width,
        "resolutionHeight": resolution_height,
        "duration": duration
    }


def set_settings(frames, resolution, comp_ids=None, print_msg=True):
    """Sets number of frames and resolution to selected comps.

    Args:
        frames (bool): True if set frame info
        resolution (bool): True if set resolution
        comp_ids (list): specific composition ids, if empty
            it tries to look for currently selected
        print_msg (bool): True throw JS alert with msg
    """
    frame_start = frames_duration = fps = width = height = None
    current_context = get_current_context()

    folder_entity = ayon_api.get_folder_by_path(
        current_context["project_name"],
        current_context["folder_path"]
    )
    settings = get_folder_settings(folder_entity)

    msg = ''
    if frames:
        frame_start = settings["frameStart"] - settings["handleStart"]
        frames_duration = settings["duration"]
        fps = settings["fps"]
        msg += f"frame start:{frame_start}, duration:{frames_duration}, "\
               f"fps:{fps}"
    if resolution:
        width = settings["resolutionWidth"]
        height = settings["resolutionHeight"]
        msg += f"width:{width} and height:{height}"

    stub = get_stub()
    if not comp_ids:
        comps = stub.get_selected_items(True, False, False)
        comp_ids = [comp.id for comp in comps]
    if not comp_ids:
        stub.print_msg("Select at least one composition to apply settings.")
        return

    for comp_id in comp_ids:
        msg = f"Setting for comp {comp_id} " + msg
        log.debug(msg)
        stub.set_comp_properties(comp_id, frame_start, frames_duration,
                                 fps, width, height)
        if print_msg:
            stub.print_msg(msg)
