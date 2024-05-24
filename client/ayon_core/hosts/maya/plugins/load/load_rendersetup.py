# -*- coding: utf-8 -*-
"""Load and update RenderSetup settings.

Working with RenderSetup setting is Maya is done utilizing json files.
When this json is loaded, it will overwrite all settings on RenderSetup
instance.
"""

import json
import sys
import six
import contextlib

from ayon_core.lib import BoolDef, EnumDef
from ayon_core.pipeline import (
    load,
    get_representation_path
)
from ayon_core.hosts.maya.api import lib
from ayon_core.hosts.maya.api.pipeline import containerise

from maya import cmds
import maya.app.renderSetup.model.renderSetup as renderSetup


@contextlib.contextmanager
def mark_all_imported(enabled):
    """Mark all imported nodes accepted by removing the `imported` attribute"""
    if not enabled:
        yield
        return

    node_types = cmds.pluginInfo("renderSetup", query=True, dependNode=True)

    # Get node before load, then we can disable `imported`
    # attribute on all new render setup layers after import
    before = cmds.ls(type=node_types, long=True)
    try:
        yield
    finally:
        after = cmds.ls(type=node_types, long=True)
        for node in (node for node in after if node not in before):
            if cmds.attributeQuery("imported",
                                   node=node,
                                   exists=True):
                plug = "{}.imported".format(node)
                if cmds.getAttr(plug):
                    cmds.deleteAttr(plug)


class RenderSetupLoader(load.LoaderPlugin):
    """Load json preset for RenderSetup overwriting current one."""

    product_types = {"rendersetup"}
    representations = {"json"}
    defaults = ['Main']

    label = "Load RenderSetup template"
    icon = "tablet"
    color = "orange"

    options = [
        BoolDef("accept_import",
                label="Accept import on load",
                tooltip=(
                  "By default importing or pasting Render Setup collections "
                  "will display them italic in the Render Setup list.\nWith "
                  "this enabled the load will directly mark the import "
                  "'accepted' and remove the italic view."
                ),
                default=True),
        BoolDef("load_managed",
                label="Load Managed",
                tooltip=(
                  "Containerize the rendersetup on load so it can be "
                  "'updated' later."
                ),
                default=True),
        EnumDef("import_mode",
                label="Import mode",
                items={
                    renderSetup.DECODE_AND_OVERWRITE: (
                        "Flush existing render setup and "
                        "add without any namespace"
                    ),
                    renderSetup.DECODE_AND_MERGE: (
                        "Merge with the existing render setup objects and "
                        "rename the unexpected objects"
                    ),
                    renderSetup.DECODE_AND_RENAME: (
                        "Renaming all decoded render setup objects to not "
                        "conflict with the existing render setup"
                    ),
                },
                default=renderSetup.DECODE_AND_OVERWRITE)
    ]

    def load(self, context, name, namespace, data):
        """Load RenderSetup settings."""

        path = self.filepath_from_context(context)

        accept_import = data.get("accept_import", True)
        import_mode = data.get("import_mode", renderSetup.DECODE_AND_OVERWRITE)

        self.log.info(">>> loading json [ {} ]".format(path))
        with mark_all_imported(accept_import):
            with open(path, "r") as file:
                renderSetup.instance().decode(
                    json.load(file), import_mode, None)

        if data.get("load_managed", True):
            self.log.info(">>> containerising [ {} ]".format(name))
            folder_name = context["folder"]["name"]
            namespace = namespace or lib.unique_namespace(
                folder_name + "_",
                prefix="_" if folder_name[0].isdigit() else "",
                suffix="_",
            )

            return containerise(
                name=name,
                namespace=namespace,
                nodes=[],
                context=context,
                loader=self.__class__.__name__)

    def remove(self, container):
        """Remove RenderSetup settings instance."""
        container_name = container["objectName"]

        self.log.info("Removing '%s' from Maya.." % container["name"])

        container_content = cmds.sets(container_name, query=True) or []
        nodes = cmds.ls(container_content, long=True)

        nodes.append(container_name)

        try:
            cmds.delete(nodes)
        except ValueError:
            # Already implicitly deleted by Maya upon removing reference
            pass

    def update(self, container, context):
        """Update RenderSetup setting by overwriting existing settings."""
        lib.show_message(
            "Render setup update",
            "Render setup setting will be overwritten by new version. All "
            "setting specified by user not included in loaded version "
            "will be lost.")
        repre_entity = context["representation"]
        path = get_representation_path(repre_entity)
        with open(path, "r") as file:
            try:
                renderSetup.instance().decode(
                    json.load(file), renderSetup.DECODE_AND_OVERWRITE, None)
            except Exception:
                self.log.error("There were errors during loading")
                six.reraise(*sys.exc_info())

        # Update metadata
        node = container["objectName"]
        cmds.setAttr("{}.representation".format(node),
                     repre_entity["id"],
                     type="string")
        self.log.info("... updated")

    def switch(self, container, context):
        """Switch representations."""
        self.update(container, context)
