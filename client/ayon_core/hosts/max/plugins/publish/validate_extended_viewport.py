# -*- coding: utf-8 -*-
import pyblish.api
from ayon_core.pipeline import PublishValidationError
from pymxs import runtime as rt


class ValidateExtendedViewport(pyblish.api.ContextPlugin):
    """Validate if the first viewport is an extended viewport."""

    order = pyblish.api.ValidatorOrder
    families = ["review"]
    hosts = ["max"]
    label = "Validate Extended Viewport"

    def process(self, context):
        try:
            rt.viewport.activeViewportEx(1)
        except RuntimeError:
            raise PublishValidationError(
                "Please make sure one viewport is not an extended viewport",
                description = (
                        "Please make sure at least one viewport is not an "
                        "extended viewport but a 3dsmax supported viewport "
                        "i.e camera/persp/orthographic view.\n\n"
                        "To rectify it, please go to view in the top menubar, "
                        "go to Views -> Viewports Configuration -> Layout and "
                        "right click on one of the panels to change it."
                ))

