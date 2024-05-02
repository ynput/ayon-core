import traceback
import os

import maya.cmds as cmds

import pyblish.util

from ayon_core.pipeline import (
    registered_host,
    get_current_folder_path,
    get_current_task_name
)
from ayon_core.pipeline.create import CreateContext
from ayon_core.hosts.maya.api.workfile_template_builder import (
    MayaTemplateBuilder
)
from ayon_core.hosts.maya.api.lib import set_attribute


# Needed for transition phase for asset/subset renaming. Can be hardcoded once
# transition is done.
product_key_name = "productName"
product_type_key_name = "productType"


def test_create():
    """Test re-creating instances in workfile.
    TODO:
        - Arnold Scene Source
        - Assembly
        - Animation
        - Camera Rig
        - Layout
        - Matchmove
        - Maya USD
        - Multi-shot Layout
        - Multiverse Look
        - Multiverse USD Asset
        - Multiverse USD Composition
        - Multiverse USD Override
        - Proxy Alembic
        - Redshift Proxy
        - Set Dress
        - Unreal - Skeletal Mesh
        - Unreal - Static Mesh
        - Unreal - Yeti Cache
        - Vray Proxy
        - Vray Scene
        - Xgen
        - Yeti Cache
        - Yeti Rig
    """

    host = registered_host()
    context = CreateContext(host)
    create_data = []
    instances_to_remove = []
    for instance in context.instances:
        # Ignoring "workfile" instance cause we cant recreate that while inside
        # it.
        if instance.data[product_type_key_name] == "workfile":
            continue

        creator_plugin = context.creators[instance.data["creator_identifier"]]

        instance_data_keys = [
            "variant",
            product_type_key_name
        ]
        instance_data = {x: instance.data[x] for x in instance_data_keys}
        instance_data["task"] = get_current_task_name()
        instance_data["folderPath"] = get_current_folder_path()

        hierarchy = {}
        if "instance_node" in instance.data:
            members = cmds.sets(instance.data["instance_node"], query=True)
            hierarchy[instance.data["instance_node"]] = cmds.ls(
                members, type="dagNode"
            )
            for set in cmds.ls(members, type="objectSet"):
                hierarchy[set] = cmds.sets(set, query=True)

        creator_attributes = {}
        for key, value in instance.data["creator_attributes"].items():
            creator_attributes[key] = value

        create_data.append(
            {
                "plugin": creator_plugin,
                "hierarchy": hierarchy,
                "args": [
                    instance.data[product_key_name],
                    instance_data,
                    {"use_selection": False}
                ],
                "creator_attributes": creator_attributes
            }
        )

        instances_to_remove.append(instance)

    context.remove_instances(instances_to_remove)

    for data in create_data:
        instance = data["plugin"].create(*data["args"])
        for set, nodes in data["hierarchy"].items():
            if not nodes:
                continue

            cmds.sets(nodes, forceElement=set)
        if instance:
            for key, value in data["creator_attributes"].items():
                set_attribute(key, value, instance.data["instance_node"])

    print("Create was successfull!")


def recursive_validate(valid_action_names):
    """ Recursively validate until until it is either successfull or there are
    no more approved actions to run in which case its failing.
    """
    context = pyblish.api.Context()
    context.data["create_context"] = CreateContext(registered_host())
    context = pyblish.util.collect(context)
    pyblish.util.validate(context)

    success = True
    actions_to_run = []
    for result in context.data["results"]:
        if result["success"]:
            continue

        success = False

        for action in result["plugin"].actions:
            if action.__name__ not in valid_action_names:
                continue
            actions_to_run.append(action)
            action().process(context, result["plugin"])

    if not success and not actions_to_run:
        return False, context

    if success:
        return True, context

    return recursive_validate(valid_action_names)


def create_error_report(context):
    error_message = ""
    for result in context.data["results"]:
        if result["success"]:
            continue

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

    return error_message


def test_publish():
    """Test publishing."""
    success, context = recursive_validate(
        ["RepairAction", "GenerateUUIDsOnInvalidAction"]
    )

    assert success, create_error_report(context)

    # Validation should be successful so running a complete publish.
    context = pyblish.util.publish()
    success = True
    for result in context.data["results"]:
        if not result["success"]:
            success = False
            break

    assert success, create_error_report(context)

    print("Publish was successfull!")


def test_load():
    """Test loading with placeholders.
    TODO:
        - hero versions are not loaded
        - Look
        - Review
        - Arnold Scene Source
        - Animation
        - Assembly
        - Camera Rig
        - Layout
        - Matchmove
        - Maya USD
        - Multi-shot Layout
        - Multiverse Look
        - Multiverse USD Asset
        - Multiverse USD Composition
        - Multiverse USD Override
        - Proxy Alembic
        - Redshift Proxy
        - Set Dress
        - Unreal - Skeletal Mesh
        - Unreal - Static Mesh
        - Unreal - Yeti Cache
        - Vray Proxy
        - Vray Scene
        - Xgen
        - Yeti Cache
        - Yeti Rig
    """
    builder = MayaTemplateBuilder(registered_host())
    success, placeholders = builder.populate_scene_placeholders(
        keep_placeholders=True
    )

    error_message = ""

    if not placeholders:
        error_message = "No placeholders found to test loading."

    for placeholder in placeholders:
        for err in placeholder.get_errors():
            msg = "Failed to process placeholder \"{}\" with plugin \"{}\""
            error_message += msg.format(
                placeholder.scene_identifier,
                placeholder.plugin.__class__.__name__
            )
            formatted_traceback = "".join(
                traceback.format_exception(
                    type(err),
                    err,
                    err.__traceback__
                )
            )
            error_message += "\n" + formatted_traceback

    assert success, error_message

    print("Load was successfull!")