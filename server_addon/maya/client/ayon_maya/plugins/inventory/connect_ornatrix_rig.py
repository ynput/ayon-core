import os
import json
from collections import defaultdict

from maya import cmds, mel

from ayon_core.pipeline import (
    InventoryAction,
    get_repres_contexts,
    get_representation_path,
)


class ConnectOrnatrixRig(InventoryAction):
    """Connect Ornatrix Rig with an animation or pointcache."""

    label = "Connect Ornatrix Rig"
    icon = "link"
    color = "white"

    def process(self, containers):
        # Categorize containers by product type.
        containers_by_product_type = defaultdict(list)
        repre_ids = {
            container["representation"]
            for container in containers
        }
        repre_contexts_by_id = get_repres_contexts(repre_ids)
        for container in containers:
            repre_id = container["representation"]
            repre_context = repre_contexts_by_id[repre_id]

            product_type = repre_context["product"]["productType"]

            containers_by_product_type.setdefault(product_type, [])
            containers_by_product_type[product_type].append(container)

        # Validate to only 1 source container.
        source_containers = containers_by_product_type.get("animation", [])
        source_containers += containers_by_product_type.get("pointcache", [])
        source_container_namespaces = [
            x["namespace"] for x in source_containers
        ]
        message = (
            "{} animation containers selected:\n\n{}\n\nOnly select 1 of type "
            "\"animation\" or \"pointcache\".".format(
                len(source_containers), source_container_namespaces
            )
        )
        if len(source_containers) != 1:
            self.display_warning(message)
            return

        source_container = source_containers[0]
        source_repre_id = source_container["representation"]
        source_namespace = source_container["namespace"]

        # Validate source representation is an alembic.
        source_path = get_representation_path(
            repre_contexts_by_id[source_repre_id]["representation"]
        ).replace("\\", "/")
        message = "Animation container \"{}\" is not an alembic:\n{}".format(
            source_container["namespace"], source_path
        )
        if not source_path.endswith(".abc"):
            self.display_warning(message)
            return

        ox_rig_containers = containers_by_product_type.get("oxrig")
        if not ox_rig_containers:
            self.display_warning(
                "Select at least one oxrig container"
            )
            return
        source_nodes = []
        for container in ox_rig_containers:
            repre_id = container["representation"]
            maya_file = get_representation_path(
                repre_contexts_by_id[repre_id]["representation"]
            )
            _, ext = os.path.splitext(maya_file)
            settings_file = maya_file.replace(
                ext, ".rigsettings")
            if not os.path.exists(settings_file):
                continue
            with open(settings_file, "r") as fp:
                source_nodes = json.load(fp)

            grooms_file = maya_file.replace(ext, ".oxg.zip")
            grooms_file = grooms_file.replace("\\", "/")
            # Compare loaded connections to scene.
            for node in source_nodes:
                node_name = node.get("node").replace("|", "")
                target_node = cmds.ls(f"{source_namespace}:{node_name}")
                if not target_node:
                    self.display_warning(
                        "No target node found "
                        "in \"animation\" or \"pointcache\"."
                    )
                    return
                mel.eval(f'OxLoadGroom -path "{grooms_file}";')

    def display_warning(self, message, show_cancel=False):
        """Show feedback to user.

        Returns:
            bool
        """

        from qtpy import QtWidgets

        accept = QtWidgets.QMessageBox.Ok
        if show_cancel:
            buttons = accept | QtWidgets.QMessageBox.Cancel
        else:
            buttons = accept

        state = QtWidgets.QMessageBox.warning(
            None,
            "",
            message,
            buttons=buttons,
            defaultButton=accept
        )

        return state == accept
