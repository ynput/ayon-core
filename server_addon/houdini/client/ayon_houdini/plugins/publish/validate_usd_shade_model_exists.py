# -*- coding: utf-8 -*-
import re

import ayon_api
from ayon_core.pipeline.publish import (
    ValidateContentsOrder,
    KnownPublishError,
    PublishValidationError,
)

from ayon_houdini.api import plugin


class ValidateUSDShadeModelExists(plugin.HoudiniInstancePlugin):
    """Validate the Instance has no current cooking errors."""

    order = ValidateContentsOrder
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

        product_entity = ayon_api.get_product_by_name(
            project_name,
            model_product_name,
            folder_entity["id"],
            fields={"id"}
        )
        if not product_entity:
            raise PublishValidationError(
                ("USD Model product not found: "
                 "{} ({})").format(model_product_name, folder_path),
                title=self.label
            )
