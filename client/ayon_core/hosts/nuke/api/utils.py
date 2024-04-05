import os
import re
import traceback
from datetime import datetime
import shutil

import nuke

from pyblish import util
from qtpy import QtWidgets

from ayon_core import resources
from ayon_core.pipeline import registered_host
from ayon_core.tools.utils import show_message_dialog


def set_context_favorites(favorites=None):
    """ Adding favorite folders to nuke's browser

    Arguments:
        favorites (dict): couples of {name:path}
    """
    favorites = favorites or {}
    icon_path = resources.get_resource("icons", "folder-favorite.png")
    for name, path in favorites.items():
        nuke.addFavoriteDir(
            name,
            path,
            nuke.IMAGE | nuke.SCRIPT | nuke.GEO,
            icon=icon_path)


def get_node_outputs(node):
    '''
    Return a dictionary of the nodes and pipes that are connected to node
    '''
    dep_dict = {}
    dependencies = node.dependent(nuke.INPUTS | nuke.HIDDEN_INPUTS)
    for d in dependencies:
        dep_dict[d] = []
        for i in range(d.inputs()):
            if d.input(i) == node:
                dep_dict[d].append(i)
    return dep_dict


def is_node_gizmo(node):
    '''
    return True if node is gizmo
    '''
    return 'gizmo_file' in node.knobs()


def gizmo_is_nuke_default(gizmo):
    '''Check if gizmo is in default install path'''
    plug_dir = os.path.join(os.path.dirname(
        nuke.env['ExecutablePath']), 'plugins')
    return gizmo.filename().startswith(plug_dir)


def bake_gizmos_recursively(in_group=None):
    """Converting a gizmo to group

    Arguments:
        is_group (nuke.Node)[optonal]: group node or all nodes
    """
    from .lib import maintained_selection
    if in_group is None:
        in_group = nuke.Root()
    # preserve selection after all is done
    with maintained_selection():
        # jump to the group
        with in_group:
            for node in nuke.allNodes():
                if is_node_gizmo(node) and not gizmo_is_nuke_default(node):
                    with node:
                        outputs = get_node_outputs(node)
                        group = node.makeGroup()
                        # Reconnect inputs and outputs if any
                        if outputs:
                            for n, pipes in outputs.items():
                                for i in pipes:
                                    n.setInput(i, group)
                        for i in range(node.inputs()):
                            group.setInput(i, node.input(i))
                        # set node position and name
                        group.setXYpos(node.xpos(), node.ypos())
                        name = node.name()
                        nuke.delete(node)
                        group.setName(name)
                        node = group

                if node.Class() == "Group":
                    bake_gizmos_recursively(node)


def colorspace_exists_on_node(node, colorspace_name):
    """ Check if colorspace exists on node

    Look through all options in the colorspace knob, and see if we have an
    exact match to one of the items.

    Args:
        node (nuke.Node): nuke node object
        colorspace_name (str): color profile name

    Returns:
        bool: True if exists
    """
    try:
        colorspace_knob = node['colorspace']
    except ValueError:
        # knob is not available on input node
        return False

    return colorspace_name in get_colorspace_list(colorspace_knob)


def get_colorspace_list(colorspace_knob):
    """Get available colorspace profile names

    Args:
        colorspace_knob (nuke.Knob): nuke knob object

    Returns:
        list: list of strings names of profiles
    """
    results = []

    # This pattern is to match with roles which uses an indentation and
    # parentheses with original colorspace. The value returned from the
    # colorspace is the string before the indentation, so we'll need to
    # convert the values to match with value returned from the knob,
    # ei. knob.value().
    pattern = r".*\t.* \(.*\)"
    for colorspace in nuke.getColorspaceList(colorspace_knob):
        match = re.search(pattern, colorspace)
        if match:
            results.append(colorspace.split("\t", 1)[0])
        else:
            results.append(colorspace)

    return results


def is_headless():
    """
    Returns:
        bool: headless
    """
    return QtWidgets.QApplication.instance() is None


def create_error_report(context):
    error_message = ""
    success = True
    for result in context.data["results"]:
        if result["success"]:
            continue

        success = False

        err = result["error"]
        formatted_traceback = "".join(
            traceback.format_exception(
                type(err),
                err,
                err.__traceback__
            )
        )
        fname = result["plugin"].__module__
        if 'File "<string>", line' in formatted_traceback:
            _, lineno, func, msg = err.traceback
            fname = os.path.abspath(fname)
            formatted_traceback = formatted_traceback.replace(
                'File "<string>", line',
                'File "{0}", line'.format(fname)
            )

        err = result["error"]
        error_message += "\n"
        error_message += formatted_traceback

    return success, error_message


def submit_headless_farm(node):
    # Ensure code is executed in root context.
    if nuke.root() == nuke.thisNode():
        _submit_headless_farm(node)
    else:
        # If not in root context, move to the root context and then execute the
        # code.
        with nuke.root():
            _submit_headless_farm(node)


def _submit_headless_farm(node):
    context = util.collect()

    success, error_report = create_error_report(context)

    if not success:
        show_message_dialog(
            "Collection Errors", error_report, level="critical"
        )
        return

    # Find instance for node and workfile.
    instance = None
    instance_workfile = None
    for Instance in context:
        if Instance.data["family"] == "workfile":
            instance_workfile = Instance
            continue

        instance_node = Instance.data["transientData"]["node"]
        if node.name() == instance_node.name():
            instance = Instance
        else:
            Instance.data["active"] = False

    if instance is None:
        show_message_dialog(
            "Collection Error",
            "Could not find the instance from the node.",
            level="critical"
        )
        return

    # Enable for farm publishing.
    instance.data["farm"] = True
    instance.data["transfer"] = False

    # Clear the families as we only want the main family, ei. no review etc.
    instance.data["families"] = []

    # Use the workfile instead of published.
    publish_attributes = instance.data["publish_attributes"]
    publish_attributes["NukeSubmitDeadline"]["use_published_workfile"] = False

    # Disable version validation.
    instance.data.pop("latestVersion")
    instance_workfile.data.pop("latestVersion")

    # Validate
    util.validate(context)

    success, error_report = create_error_report(context)

    if not success:
        show_message_dialog(
            "Validation Errors", error_report, level="critical"
        )
        return

    # Extraction.
    util.extract(context)

    success, error_report = create_error_report(context)

    if not success:
        show_message_dialog(
            "Extraction Errors", error_report, level="critical"
        )
        return

    # Copy the workfile to a timestamped copy.
    host = registered_host()
    current_datetime = datetime.now()
    formatted_timestamp = current_datetime.strftime("%Y%m%d%H%M%S")
    base, ext = os.path.splitext(host.current_file())

    directory = os.path.join(os.path.dirname(base), "farm_submissions")
    if not os.path.exists(directory):
        os.makedirs(directory)

    filename = "{}_{}{}".format(
        os.path.basename(base), formatted_timestamp, ext
    )
    path = os.path.join(directory, filename).replace("\\", "/")
    context.data["currentFile"] = path
    shutil.copy(host.current_file(), path)

    # Continue to submission.
    util.integrate(context)

    success, error_report = create_error_report(context)

    if not success:
        show_message_dialog(
            "Extraction Errors", error_report, level="critical"
        )
        return

    show_message_dialog(
        "Submission Successful", "Submission to the farm was successful."
    )
