# -*- coding: utf-8 -*-
import pyblish.api

from ayon_core.pipeline.publish import (
    ValidateContentsOrder,
    PublishValidationError,
    OptionalPyblishPluginMixin,
)
from ayon_core.client import get_subset_by_name


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
        subset_doc = get_subset_by_name(
            project_name, instance.data["productName"], folder_id)

        if subset_doc:
            raise PublishValidationError(
                "Subset to be published already exists.",
                title=self.label
            )
