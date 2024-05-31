# -*- coding: utf-8 -*-
import os

import pyblish.api
from ayon_core.pipeline import PublishValidationError

from ayon_houdini.api import plugin


class ValidateUSDRenderProductNames(plugin.HoudiniInstancePlugin):
    """Validate USD Render Product names are correctly set absolute paths."""

    order = pyblish.api.ValidatorOrder
    families = ["usdrender"]
    label = "Validate USD Render Product Names"
    optional = True

    def process(self, instance):

        invalid = []
        for filepath in instance.data["files"]:

            if not filepath:
                invalid.append("Detected empty output filepath.")

            if not os.path.isabs(filepath):
                invalid.append(
                    "Output file path is not absolute path: %s" % filepath
                )

        if invalid:
            for message in invalid:
                self.log.error(message)
            raise PublishValidationError(
                "USD Render Paths are invalid.", title=self.label)
