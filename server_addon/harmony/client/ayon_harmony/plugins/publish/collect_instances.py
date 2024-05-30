# -*- coding: utf-8 -*-
"""Collect instances in Harmony."""
import json

import pyblish.api
import ayon_harmony.api as harmony


class CollectInstances(pyblish.api.ContextPlugin):
    """Gather instances by nodes metadata.

    This collector takes into account assets that are associated with
    a composite node and marked with a unique identifier.

    Identifier:
        id (str): "ayon.create.instance"
    """

    label = "Instances"
    order = pyblish.api.CollectorOrder
    hosts = ["harmony"]
    product_type_mapping = {
        "render": ["review", "ftrack"],
        "harmony.template": [],
        "palette": ["palette", "ftrack"]
    }

    pair_media = True

    def process(self, context):
        """Plugin entry point.

        Args:
            context (:class:`pyblish.api.Context`): Context data.

        """
        nodes = harmony.send(
            {"function": "node.subNodes", "args": ["Top"]}
        )["result"]

        for node in nodes:
            data = harmony.read(node)

            # Skip non-tagged nodes.
            if not data:
                continue

            # Skip containers.
            if "container" in data["id"]:
                continue

            product_type = data.get("productType")
            if product_type is None:
                product_type = data["family"]
                data["productType"] = product_type
            data["family"] = product_type

            # skip render farm product type as it is collected separately
            if product_type == "renderFarm":
                continue

            instance = context.create_instance(node.split("/")[-1])
            instance.data.update(data)
            instance.data["setMembers"] = [node]
            instance.data["publish"] = harmony.send(
                {"function": "node.getEnable", "args": [node]}
            )["result"]

            families = [product_type]
            families.extend(self.product_type_mapping[product_type])
            instance.data["families"] = families

            # If set in plugin, pair the scene Version in ftrack with
            # thumbnails and review media.
            if (self.pair_media and product_type == "scene"):
                context.data["scene_instance"] = instance

            # Produce diagnostic message for any graphical
            # user interface interested in visualising it.
            self.log.info(
                "Found: \"{0}\": \n{1}".format(
                    instance.data["name"], json.dumps(instance.data, indent=4)
                )
            )
