import traceback
import os

import maya.cmds as cmds

import pyblish.util

from ayon_core.pipeline import registered_host
from ayon_core.pipeline.create import CreateContext
from ayon_core.hosts.maya.api.workfile_template_builder import (
    MayaTemplateBuilder
)


# Needed for transition phase for asset/subset renaming. Can be hardcoded once
# transition is done.
product_key_name = "productName"
product_type_key_name = "productType"


def test_create():
    """Test re-creating instances in workfile.
    TODO:
        - Arnold Scene Source
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
        - Pointcache
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
            "folderPath",
            "task",
            "variant",
            product_type_key_name
        ]
        instance_data = {x: instance.data[x] for x in instance_data_keys}

        hierarchy = {}
        if "instance_node" in instance.data:
            members = cmds.sets(instance.data["instance_node"], query=True)
            hierarchy[instance.data["instance_node"]] = cmds.ls(
                members, type="dagNode"
            )
            for set in cmds.ls(members, type="objectSet"):
                hierarchy[set] = cmds.sets(set, query=True)

        create_data.append(
            {
                "plugin": creator_plugin,
                "hierarchy": hierarchy,
                "args": [
                    instance.data[product_key_name],
                    instance_data,
                    {"use_selection": False}
                ]
            }
        )

        instances_to_remove.append(instance)

    context.remove_instances(instances_to_remove)

    for data in create_data:
        data["plugin"].create(*data["args"])
        for set, nodes in data["hierarchy"].items():
            if not nodes:
                continue

            cmds.sets(nodes, forceElement=set)

    print("Create was successfull!")


def test_publish():
    """Test publishing."""

    context = pyblish.util.publish()
    success = True
    error_message = ""
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

    assert success, error_message
    print("Publish was successfull!")


def test_load():
    """Test loading with placeholders.
    TODO:
        - hero versions are not loaded
        - Look
        - Review
        - Arnold Scene Source
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
        - Pointcache
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
    builder.populate_scene_placeholders(keep_placeholders=True)
    print("Load was successfull!")
