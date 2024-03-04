# -*- coding: utf-8 -*-
import re

import pyblish.api

from ayon_core.client import get_subset_by_name
from ayon_core.pipeline.publish import (
    ValidateContentsOrder,
    KnownPublishError,
    PublishValidationError,
)


class ValidateUSDShadeModelExists(pyblish.api.InstancePlugin):
    """Validate the Instance has no current cooking errors."""

    order = ValidateContentsOrder
    hosts = ["houdini"]
    families = ["usdShade"]
    label = "USD Shade model exists"

    def process(self, instance):
        project_name = instance.context.data["projectName"]
        folder_path = instance.data["folderPath"]
        product_name = instance.data["productName"]

        # Assume shading variation starts after a dot separator
        shade_product_name = product_name.split(".", 1)[0]
        model_product_name = re.sub(
            "^usdShade", "usdModel", shade_product_name
        )

        folder_entity = instance.data.get("folderEntity")
        if not folder_entity:
            raise KnownPublishError(
                "Folder entity is not filled on instance."
            )

        subset_doc = get_subset_by_name(
            project_name,
            model_product_name,
            folder_entity["id"],
            fields=["_id"]
        )
        if not subset_doc:
            raise PublishValidationError(
                ("USD Model product not found: "
                 "{} ({})").format(model_product_name, folder_path),
                title=self.label
            )
