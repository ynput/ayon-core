import traceback

import maya.cmds as cmds

import pyblish.util

from ayon_core.pipeline import (
    registered_host,
    get_current_folder_path,
    get_current_task_name
)
from ayon_core.pipeline.create import CreateContext
from ayon_maya.api.workfile_template_builder import (
    MayaTemplateBuilder
)

from . import lib


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
            print(members)
            hierarchy[instance.data["instance_node"]] = cmds.ls(
                members, type="dagNode"
            )
            for set in cmds.ls(members, type="objectSet"):
                hierarchy[set] = cmds.sets(set, query=True)

        creator_attributes = {}
        for key, value in instance.data["creator_attributes"].items():
            creator_attributes[key] = value
        creator_identifier = instance.data["creator_identifier"]
        create_data.append(
            {
                "creator_identifier": creator_identifier,
                "hierarchy": hierarchy,
                "creator_attributes": creator_attributes
            }
        )
        instances_to_remove.append(instance)

    context.remove_instances(instances_to_remove)

    for data in create_data:
        created_instance = context.create(
            creator_identifier=data["creator_identifier"],
            variant="Main",
            pre_create_data={"use_selection": True}
        )
        for set, nodes in data["hierarchy"].items():
            if not nodes:
                continue

            cmds.sets(nodes, forceElement=set)
        if created_instance:
            for key, value in data["creator_attributes"].items():
               created_instance.creator_attributes[key] = value

        context.save_changes()
    print("Create was successful!")


def test_publish():
    """Test publishing."""
    success, context = lib.recursive_validate(
        ["RepairAction", "GenerateUUIDsOnInvalidAction"]
    )

    assert success, lib.create_error_report(context)

    # Validation should be successful so running a complete publish.
    context = pyblish.util.publish()
    success = True
    for result in context.data["results"]:
        if not result["success"]:
            success = False
            break

    assert success, lib.create_error_report(context)

    print("Publish was successful!")


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

    print("Load was successful!")
