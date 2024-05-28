import os
import re

import nuke

import pyblish.util
import pyblish.api
from qtpy import QtWidgets

from ayon_core import resources
from ayon_core.pipeline import registered_host
from ayon_core.tools.utils import show_message_dialog
from ayon_core.pipeline.create import CreateContext


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


def submit_render_on_farm(node):
    # Ensure code is executed in root context.
    if nuke.root() == nuke.thisNode():
        _submit_render_on_farm(node)
    else:
        # If not in root context, move to the root context and then execute the
        # code.
        with nuke.root():
            _submit_render_on_farm(node)


def _submit_render_on_farm(node):
    """Render on farm submission

    This function prepares the context for farm submission, validates it,
    extracts relevant data, copies the current workfile to a timestamped copy,
    and submits the job to the farm.

    Args:
        node (Node): The node for which the farm submission is being made.
    """

    host = registered_host()
    create_context = CreateContext(host)

    # Ensure CreateInstance is enabled.
    for instance in create_context.instances:
        if node.name() != instance.transient_data["node"].name():
            continue

        instance.data["active"] = True

    context = pyblish.api.Context()
    context.data["create_context"] = create_context
    # Used in pyblish plugin to determine which instance to publish.
    context.data["node_name"] = node.name()
    # Used in pyblish plugins to determine whether to run or not.
    context.data["render_on_farm"] = True

    # Since we need to bypass version validation and incrementing, we need to
    # remove the plugins from the list that are responsible for these tasks.
    plugins = pyblish.api.discover()
    blacklist = ["IncrementScriptVersion", "ValidateVersion"]
    plugins = [
        plugin
        for plugin in plugins
        if plugin.__name__ not in blacklist
    ]

    context = pyblish.util.publish(context, plugins=plugins)

    error_message = ""
    success = True
    for result in context.data["results"]:
        if result["success"]:
            continue

        success = False

        err = result["error"]
        error_message += "\n"
        error_message += err.formatted_traceback

    if not success:
        show_message_dialog(
            "Publish Errors", error_message, level="critical"
        )
        return

    show_message_dialog(
        "Submission Successful", "Submission to the farm was successful."
    )
