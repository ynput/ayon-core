import re
import os

import hou
import pxr.UsdRender

import pyblish.api

from ayon_core.hosts.houdini.api.usd import (
    get_usd_render_rop_rendersettings
)


class CollectRenderProducts(pyblish.api.InstancePlugin):
    """Collect USD Render Products.

    The render products are collected from the USD Render ROP node by detecting
    what the selected Render Settings prim path is, then finding those
    Render Settings in the USD Stage and collecting the targeted Render
    Products and their expected filenames.

    Note: Product refers USD Render Product, not to an AYON Product

    """

    label = "Collect Render Products"
    order = pyblish.api.CollectorOrder + 0.4
    hosts = ["houdini"]
    families = ["usdrender"]

    def process(self, instance):

        rop_node = hou.node(instance.data["instance_node"])
        node = instance.data.get("output_node")
        if not node:
            rop_path = rop_node.path()
            self.log.error(
                "No output node found. Make sure to connect a valid "
                "input to the USD ROP: %s" % rop_path
            )
            return

        override_output_image = rop_node.evalParm("outputimage")

        filenames = []
        files_by_product = {}
        stage = node.stage()
        for prim_path in self.get_render_products(rop_node, stage):
            prim = stage.GetPrimAtPath(prim_path)
            if not prim or not prim.IsA(pxr.UsdRender.Product):
                self.log.warning("Found invalid render product path "
                                 "configured in render settings that is not a "
                                 "Render Product prim: %s", prim_path)
                continue

            render_product = pxr.UsdRender.Product(prim)
            # Get Render Product Name
            if override_output_image:
                name = override_output_image
            else:
                # We force taking it from any random time sample as opposed to
                # "default" that the USD Api falls back to since that won't
                # return time sampled values if they were set per time sample.
                name = render_product.GetProductNameAttr().Get(time=0)

            dirname = os.path.dirname(name)
            basename = os.path.basename(name)

            dollarf_regex = r"(\$F([0-9]?))"
            if re.match(dollarf_regex, basename):
                # TODO: Confirm this actually is allowed USD stages and HUSK
                # Substitute $F
                def replace(match):
                    """Replace $F4 with padded #."""
                    padding = int(match.group(2)) if match.group(2) else 1
                    return "#" * padding

                filename_base = re.sub(dollarf_regex, replace, basename)
                filename = os.path.join(dirname, filename_base)
            else:
                # Last group of digits in the filename before the extension
                # The frame number must always be prefixed by underscore or dot
                # Allow product names like:
                #   - filename.1001.exr
                #   - filename.1001.aov.exr
                #   - filename.aov.1001.exr
                #   - filename_1001.exr
                frame_regex = r"(.*[._])(\d+)(?!.*\d)(.*\.[A-Za-z0-9]+$)"

                # It may be the case that the current USD stage has stored
                # product name samples (e.g. when loading a USD file with
                # time samples) where it does not refer to e.g. $F4. And thus
                # it refers to the actual path like /path/to/frame.1001.exr
                # TODO: It would be better to maybe sample product name
                #  attribute `ValueMightBeTimeVarying` and if so get it per
                #  frame using `attr.Get(time=frame)` to ensure we get the
                #  actual product name set at that point in time?
                # Substitute basename.0001.ext
                def replace(match):
                    head, frame, tail = match.groups()
                    padding = "#" * len(frame)
                    return head + padding + tail

                filename_base = re.sub(frame_regex, replace, basename)
                filename = os.path.join(dirname, filename_base)
                filename = filename.replace("\\", "/")

            assert "#" in filename, (
                "Couldn't resolve render product name "
                "with frame number: %s" % name
            )

            filenames.append(filename)

            # TODO: Improve AOV name detection logic
            aov_identifier = self.get_aov_identifier(render_product)
            if aov_identifier in files_by_product:
                self.log.error(
                    "Multiple render products are identified as the same AOV "
                    "which means one of the two will not be ingested during"
                    "publishing. AOV: '%s'", aov_identifier
                )
                self.log.warning("Skipping Render Product: %s", render_product)

            files_by_product[aov_identifier] = self.generate_expected_files(
                instance,
                filename
            )

            aov_label = f"'{aov_identifier}' aov in " if aov_identifier else ""
            self.log.debug("Render Product %s%s", aov_label, prim_path)
            self.log.debug("Product name: %s", filename)

        # Filenames for Deadline
        instance.data["files"] = filenames
        instance.data.setdefault("expectedFiles", []).append(files_by_product)

    def get_aov_identifier(self, render_product):
        """Return the AOV identfier for a Render Product

        A Render Product does not really define what 'AOV' it is, it
        defines the product name (output path) and the render vars to
        include.

        So we need to define what in particular of a `UsdRenderProduct`
        we use to separate the AOV (and thus apply sub-grouping with).

        For now we'll consider any Render Product that only refers
        to a single rendervar that the rendervars prim name is the AOV
        otherwise we'll assume renderproduct to be a combined multilayer
        'main' layer

        Args:
            render_product (pxr.UsdRender.Product): The Render Product

        Returns:
            str: The AOV identifier

        """
        targets = render_product.GetOrderedVarsRel().GetTargets()
        if len(targets) > 1:
            # Cryptomattes usually are combined render vars, for example:
            # - crypto_asset, crypto_asset01, crypto_asset02, crypto_asset03
            # - crypto_object, crypto_object01, etc.
            # These still refer to the same AOV so we take the common prefix
            # e.g. `crypto_asset` or `crypto` (if multiple are combined)
            if all(target.name.startswith("crypto") for target in targets):
                start = os.path.commonpath([target.name for target in targets])
                return start.rstrip("_")  # remove any trailing _

            # Main layer
            return ""
        else:
            # AOV for a single var
            return targets[0].name

    def get_render_products(self, usdrender_rop, stage):
        """"The render products in the defined render settings

        Args:
            usdrender_rop (hou.Node): The Houdini USD Render ROP node.
            stage (pxr.Usd.Stage): The USD stage to find the render settings
                 in. This is usually the stage from the LOP path the USD Render
                 ROP node refers to.

        Returns:
            List[Sdf.Path]: Render Product paths enabled in the render settings

        """
        render_settings = get_usd_render_rop_rendersettings(usdrender_rop,
                                                            stage,
                                                            logger=self.log)
        if not render_settings:
            return []

        return render_settings.GetProductsRel().GetTargets()

    def generate_expected_files(self, instance, path):
        """Generate full sequence of expected files from a filepath.

        The filepath should have '#' token as placeholder for frame numbers or
        should have %04d or %d placeholders. The `#` characters indicate frame
        number and padding, e.g. #### becomes 0001 for frame 1.

        Args:
            instance (pyblish.api.Instance): The publish instance.
            path (str): The filepath to generate the list of output files for.

        Returns:
            list: Filepath per frame.

        """

        folder = os.path.dirname(path)
        filename = os.path.basename(path)

        if "#" in filename:
            def replace(match):
                return "%0{}d".format(len(match.group()))

            filename = re.sub("#+", replace, filename)

        if "%" not in filename:
            # Not a sequence, single file
            return path

        expected_files = []
        start = instance.data["frameStartHandle"]
        end = instance.data["frameEndHandle"]

        for frame in range(int(start), (int(end) + 1)):
            expected_files.append(
                os.path.join(folder, (filename % frame)).replace("\\", "/"))

        return expected_files
