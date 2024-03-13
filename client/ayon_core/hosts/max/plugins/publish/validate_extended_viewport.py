# -*- coding: utf-8 -*-
import pyblish.api
from ayon_core.pipeline import PublishValidationError
from pymxs import runtime as rt


class ValidateExtendedViewport(pyblish.api.InstancePlugin):
    """Validate if the first viewport is an extended viewport."""

    order = pyblish.api.ValidatorOrder
    families = ["review"]
    hosts = ["max"]
    label = "Validate Extended Viewport"

    def process(self, instance):
        try:
            rt.viewport.activeViewportEx(1)
        except RuntimeError:
            raise PublishValidationError(
                "Please make sure one viewport is not an extended viewport", title=self.label)

