# -*- coding: utf-8 -*-
import ayon_api
import pyblish.api

from ayon_core.pipeline.publish import (
    ValidateContentsOrder,
    PublishValidationError,
    OptionalPyblishPluginMixin,
)


class ValidateOnlineFile(OptionalPyblishPluginMixin,
                         pyblish.api.InstancePlugin):
    """Validate that product doesn't exist yet."""
    label = "Validate Existing Online Files"
    hosts = ["traypublisher"]
    families = ["online"]
    order = ValidateContentsOrder

    optional = True

    def process(self, instance):
        if not self.is_active(instance.data):
            return
        project_name = instance.context.data["projectName"]
        folder_id = instance.data["folderEntity"]["id"]
        product_entity = ayon_api.get_product_by_name(
            project_name, instance.data["productName"], folder_id)

        if product_entity:
            raise PublishValidationError(
                "Product to be published already exists.",
                title=self.label
            )
