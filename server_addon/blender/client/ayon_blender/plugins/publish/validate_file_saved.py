import bpy

import pyblish.api

from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError
)
from ayon_blender.api import plugin


class SaveWorkfileAction(pyblish.api.Action):
    """Save Workfile."""
    label = "Save Workfile"
    on = "failed"
    icon = "save"

    def process(self, context, plugin):
        bpy.ops.wm.avalon_workfiles()


class ValidateFileSaved(
    plugin.BlenderContextPlugin,
    OptionalPyblishPluginMixin
):
    """Validate that the workfile has been saved."""

    order = pyblish.api.ValidatorOrder - 0.01
    hosts = ["blender"]
    label = "Validate File Saved"
    optional = False
    # TODO rename to 'exclude_product_types'
    exclude_families = []
    actions = [SaveWorkfileAction]

    def process(self, context):
        if not self.is_active(context.data):
            return

        if not context.data["currentFile"]:
            # File has not been saved at all and has no filename
            raise PublishValidationError(
                "Current workfile has not been saved yet.\n"
                "Save the workfile before continuing."
            )

        # Do not validate workfile has unsaved changes if only instances
        # present of families that should be excluded
        product_types = {
            instance.data["productType"] for instance in context
            # Consider only enabled instances
            if instance.data.get("publish", True)
            and instance.data.get("active", True)
        }

        def is_excluded(family):
            return any(family in exclude_family
                       for exclude_family in self.exclude_families)

        if all(is_excluded(product_type) for product_type in product_types):
            self.log.debug("Only excluded families found, skipping workfile "
                           "unsaved changes validation..")
            return

        if bpy.data.is_dirty:
            raise PublishValidationError("Workfile has unsaved changes.")
