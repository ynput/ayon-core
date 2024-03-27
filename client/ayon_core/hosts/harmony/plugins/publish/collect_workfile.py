# -*- coding: utf-8 -*-
"""Collect current workfile from Harmony."""
import os
import pyblish.api

from ayon_core.pipeline.create import get_product_name


class CollectWorkfile(pyblish.api.ContextPlugin):
    """Collect current script for publish."""

    order = pyblish.api.CollectorOrder + 0.1
    label = "Collect Workfile"
    hosts = ["harmony"]

    def process(self, context):
        """Plugin entry point."""
        product_type = "workfile"
        basename = os.path.basename(context.data["currentFile"])
        task_entity = context.data["taskEntity"]
        task_name = task_type = None
        if task_entity:
            task_name = task_entity["name"]
            task_type = task_entity["taskType"]
        product_name = get_product_name(
            context.data["projectName"],
            task_name,
            task_type,
            context.data["hostName"],
            product_type,
            "",
            project_settings=context.data["project_settings"]
        )

        # Create instance
        instance = context.create_instance(product_name)
        instance.data.update({
            "productName": product_name,
            "label": basename,
            "name": basename,
            "productType": product_type,
            "family": product_type,
            "families": [product_type],
            "representations": [],
            "folderPath": context.data["folderPath"]
        })
