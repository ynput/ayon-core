# -*- coding: utf-8 -*-
"""Loader for image sequences."""
import os
import uuid
from pathlib import Path

import clique

from ayon_core.pipeline import (
    load,
    get_representation_path,
)
from ayon_core.pipeline.context_tools import is_representation_from_latest
import ayon_harmony.api as harmony


class ImageSequenceLoader(load.LoaderPlugin):
    """Load image sequences.

    Stores the imported asset in a container named after the asset.
    """

    product_types = {
        "shot",
        "render",
        "image",
        "plate",
        "reference",
        "review",
    }
    representations = {"*"}
    extensions = {"jpeg", "png", "jpg"}
    settings_category = "harmony"

    def load(self, context, name=None, namespace=None, data=None):
        """Plugin entry point.

        Args:
            context (:class:`pyblish.api.Context`): Context.
            name (str, optional): Container name.
            namespace (str, optional): Container namespace.
            data (dict, optional): Additional data passed into loader.

        """
        fname = Path(self.filepath_from_context(context))
        self_name = self.__class__.__name__
        collections, remainder = clique.assemble(
            os.listdir(fname.parent.as_posix())
        )
        files = []
        if collections:
            for f in list(collections[0]):
                files.append(fname.parent.joinpath(f).as_posix())
        else:
            files.append(fname.parent.joinpath(remainder[0]).as_posix())

        folder_name = context["folder"]["name"]
        product_name = context["product"]["name"]

        group_id = str(uuid.uuid4())
        read_node = harmony.send(
            {
                "function": f"PypeHarmony.Loaders.{self_name}.importFiles",  # noqa: E501
                "args": [
                    files,
                    folder_name,
                    product_name,
                    1,
                    group_id
                ]
            }
        )["result"]

        return harmony.containerise(
            f"{folder_name}_{product_name}",
            namespace,
            read_node,
            context,
            self_name,
            nodes=[read_node]
        )

    def update(self, container, context):
        """Update loaded containers.

        Args:
            container (dict): Container data.
            context (dict): Representation context data.

        """
        self_name = self.__class__.__name__
        node = container.get("nodes").pop()

        repre_entity = context["representation"]
        path = get_representation_path(repre_entity)
        collections, remainder = clique.assemble(
            os.listdir(os.path.dirname(path))
        )
        files = []
        if collections:
            for f in list(collections[0]):
                files.append(
                    os.path.join(
                        os.path.dirname(path), f
                    ).replace("\\", "/")
                )
        else:
            files.append(
                os.path.join(
                    os.path.dirname(path), remainder[0]
                ).replace("\\", "/")
            )

        harmony.send(
            {
                "function": f"PypeHarmony.Loaders.{self_name}.replaceFiles",
                "args": [files, node, 1]
            }
        )

        # Colour node.
        if is_representation_from_latest(repre_entity):
            harmony.send(
                {
                    "function": "PypeHarmony.setColor",
                    "args": [node, [0, 255, 0, 255]]
                })
        else:
            harmony.send(
                {
                    "function": "PypeHarmony.setColor",
                    "args": [node, [255, 0, 0, 255]]
                })

        harmony.imprint(
            node, {"representation": repre_entity["id"]}
        )

    def remove(self, container):
        """Remove loaded container.

        Args:
            container (dict): Container data.

        """
        node = container.get("nodes").pop()
        harmony.send(
            {"function": "PypeHarmony.deleteNode", "args": [node]}
        )
        harmony.imprint(node, {}, remove=True)

    def switch(self, container, context):
        """Switch loaded representations."""
        self.update(container, context)
