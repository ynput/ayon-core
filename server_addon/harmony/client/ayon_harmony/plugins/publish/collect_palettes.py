# -*- coding: utf-8 -*-
"""Collect palettes from Harmony."""
import json
import re

import pyblish.api
import ayon_harmony.api as harmony


class CollectPalettes(pyblish.api.ContextPlugin):
    """Gather palettes from scene when publishing templates."""

    label = "Palettes"
    order = pyblish.api.CollectorOrder + 0.003
    hosts = ["harmony"]

    settings_category = "harmony"

    # list of regexes for task names where collecting should happen
    allowed_tasks = []

    def process(self, context):
        """Collector entry point."""
        self_name = self.__class__.__name__
        palettes = harmony.send(
            {
                "function": f"PypeHarmony.Publish.{self_name}.getPalettes",
            })["result"]

        # skip collecting if not in allowed task
        if self.allowed_tasks:
            task_name = context.data["anatomyData"]["task"]["name"].lower()
            if (not any([re.search(pattern, task_name)
                         for pattern in self.allowed_tasks])):
                return
        folder_path = context.data["folderPath"]

        product_type = "harmony.palette"
        for name, id in palettes.items():
            instance = context.create_instance(name)
            instance.data.update({
                "id": id,
                "productType": product_type,
                "family": product_type,
                "families": [product_type],
                "folderPath": folder_path,
                "productName": "{}{}".format("palette", name)
            })
            self.log.info(
                "Created instance:\n" + json.dumps(
                    instance.data, sort_keys=True, indent=4
                )
            )
