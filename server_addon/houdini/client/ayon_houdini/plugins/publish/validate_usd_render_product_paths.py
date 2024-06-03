# -*- coding: utf-8 -*-
import os
import hou
import inspect
import pyblish.api

from ayon_core.pipeline import PublishValidationError


class ValidateUSDRenderProductPaths(pyblish.api.InstancePlugin):
    """Validate USD Render Settings refer to a valid render camera.

    The publishing logic uses a metadata `.json` in the render output images'
    folder to identify how the files should be published. To ensure multiple
    subsequent submitted versions of a scene do not override the same metadata
    json file we want to ensure the user has the render paths set up to
    contain the $HIPNAME in a parent folder.

    """
    # NOTE(colorbleed): This workflow might be relatively Colorbleed-specific
    # TODO: Preferably we find ways to make what this tries to avoid no issue
    #   itself by e.g. changing how AYON deals with these metadata json files.

    order = pyblish.api.ValidatorOrder
    families = ["usdrender"]
    hosts = ["houdini"]
    label = "Validate USD Render Product Paths"
    optional = True

    def process(self, instance):

        current_file = instance.context.data["currentFile"]

        # mimic `$HIPNAME:r` because `hou.text.collapseCommonVars can not
        # collapse it
        hipname_r = os.path.splitext(os.path.basename(current_file))[0]

        invalid = False
        for filepath in instance.data.get("files", []):
            folder = os.path.dirname(filepath)

            if hipname_r not in folder:
                filepath_raw = hou.text.collapseCommonVars(filepath, vars=[
                    "$HIP", "$JOB", "$HIPNAME"
                ])
                filepath_raw = filepath_raw.replace(hipname_r, "$HIPNAME:r")
                self.log.error("Invalid render output path:\n%s", filepath_raw)
                invalid = True

        if invalid:
            raise PublishValidationError(
                "Render path is invalid. Please make sure to include a "
                "folder with '$HIPNAME:r'.",
                title=self.label,
                description=self.get_description()
            )

    def get_description(self):
        return inspect.cleandoc(
            """### Invalid render output path

            The render output path must include the current scene name in
            a parent folder to ensure uniqueness across multiple workfile
            versions. Otherwise subsequent farm publishes could fail because
            newer versions will overwrite the metadata files of older versions.

            The easiest way to do so is to include **`$HIPNAME:r`** somewhere
            in the render product names.

            A recommended output path is for example:
            ```
            $HIP/renders/$HIPNAME:r/$OS/$HIPNAME:r.$OS.$F4.exr
            ```
            """
        )
