# -*- coding: utf-8 -*-
import inspect

import pyblish.api

from ayon_core.pipeline.publish import PublishValidationError, RepairAction
from ayon_core.hosts.houdini.api.action import SelectROPAction
from ayon_core.hosts.houdini.api.usd import get_usd_render_rop_rendersettings

import hou
import pxr
from pxr import UsdRender


class ValidateUSDRenderSingleFile(pyblish.api.InstancePlugin):
    """Validate the writing of a single USD Render Output file.

     When writing to single file with USD Render ROP make sure to write the
     output USD file from a single process to avoid overwriting it with
     different processes.
     """

    order = pyblish.api.ValidatorOrder
    families = ["usdrender"]
    hosts = ["houdini"]
    label = "Validate USD Render ROP Settings"
    actions = [SelectROPAction, RepairAction]

    def process(self, instance):
        # Get configured settings for this instance
        submission_data = (
            instance.data
            .get("publish_attributes", {})
            .get("HoudiniSubmitDeadlineUsdRender", {})
        )
        render_chunk_size = submission_data.get("chunk", 1)
        export_chunk_size = submission_data.get("export_chunk", 1)
        usd_file_per_frame = "$F" in instance.data["ifdFile"]
        frame_start_handle = instance.data["frameStartHandle"]
        frame_end_handle = instance.data["frameEndHandle"]
        num_frames = frame_end_handle - frame_start_handle + 1
        rop_node = hou.node(instance.data["instance_node"])

        # Whether ROP node is set to render all Frames within a single process
        # When this is disabled then Husk will restart completely per frame
        # no matter the chunk size.
        all_frames_at_once = rop_node.evalParm("allframesatonce")

        invalid = False
        if usd_file_per_frame:
            # USD file per frame
            # If rendering multiple frames per task and USD file has $F then
            # log a warning that the optimization will be less efficient
            # since husk will still restart per frame.
            if render_chunk_size > 1:
                self.log.debug(
                    "Render chunk size is bigger than one but export file is "
                    "a USD file per frame. Husk does not allow rendering "
                    "separate USD files in one process. As such, Husk will "
                    "restart per frame even within the chunk to render the "
                    "correct file per frame."
                )
        else:
            # Single export USD file
            # Export chunk size must be higher than the amount of frames to
            # ensure the file is written in one go on one machine and thus
            # ends up containing all frames correctly
            if export_chunk_size < num_frames:
                self.log.error(
                    "The export chunk size %s is smaller than the amount of "
                    "frames %s, so multiple tasks will try to export to "
                    "the same file. Make sure to increase chunk "
                    "size to higher than the amount of frames to render, "
                    "more than >%s",
                    export_chunk_size, num_frames, num_frames
                )
                invalid = True

            if not all_frames_at_once:
                self.log.error(
                    "Please enable 'Render All Frames With A Single Process' "
                    "on the USD Render ROP node or add $F to the USD filename",
                )
                invalid = True

        if invalid:
            raise PublishValidationError(
                "Render USD file being overwritten during export.",
                title="Render USD file overwritten",
                description=self.get_description())

    @classmethod
    def repair(cls, instance):
        # Enable all frames at once and make the frames per task
        # very large
        rop_node = hou.node(instance.data["instance_node"])
        rop_node.parm("allframesatonce").set(True)

        # Override instance setting for export chunk size
        create_context = instance.context.data["create_context"]
        created_instance = create_context.get_instance_by_id(
            instance.data["instance_id"]
        )
        created_instance.publish_attributes["HoudiniSubmitDeadlineUsdRender"]["export_chunk"] = 1000  # noqa
        create_context.save_changes()

    def get_description(self):
        return inspect.cleandoc(
            """### Render USD file configured incorrectly

            The USD render ROP is currently configured to write a single
            USD file to render instead of a file per frame.

            When that is the case, a single machine must produce that file in
            one process to avoid the file being overwritten by the other
            processes.

            We resolve that by enabling _Render All Frames With A Single
            Process_ on the ROP node and ensure the export job task size
            is larger than the amount of frames of the sequence, so the file
            gets written in one go.

            Run **Repair** to resolve this for you.

            If instead you want to write separate render USD files, please
            include $F in the USD output filename on the `ROP node > Output >
            USD Export > Output File`
            """
        )


class ValidateUSDRenderArnoldSettings(pyblish.api.InstancePlugin):
    """Validate USD Render Product names are correctly set absolute paths."""

    order = pyblish.api.ValidatorOrder
    families = ["usdrender"]
    hosts = ["houdini"]
    label = "Validate USD Render Arnold Settings"
    actions = [SelectROPAction]

    def process(self, instance):

        rop_node = hou.node(instance.data["instance_node"])
        node = instance.data.get("output_node")
        if not node:
            # No valid output node was set. We ignore it since it will
            # be validated by another plug-in.
            return

        # Check only for Arnold renderer
        renderer = rop_node.evalParm("renderer")
        if renderer != "HdArnoldRendererPlugin":
            self.log.debug("Skipping Arnold Settings validation because "
                           "renderer is set to: %s", renderer)
            return

        # Validate Arnold Product Type is enabled on the Arnold Render Settings
        # This is confirmed by the `includeAovs` attribute on the RenderProduct
        stage: pxr.Usd.Stage = node.stage()
        invalid = False
        for prim_path in instance.data.get("usdRenderProducts", []):
            prim = stage.GetPrimAtPath(prim_path)
            include_aovs = prim.GetAttribute("includeAovs")
            if not include_aovs.IsValid() or not include_aovs.Get(0):
                self.log.error(
                    "All Render Products must be set to 'Arnold Product "
                    "Type' on the Arnold Render Settings node to ensure "
                    "correct output of metadata and AOVs."
                )
                invalid = True
                break

        # Ensure 'Delegate Products' is enabled for Husk
        if not rop_node.evalParm("husk_delegateprod"):
            invalid = True
            self.log.error("USD Render ROP has `Husk > Rendering > Delegate "
                           "Products` disabled. Please enable to ensure "
                           "correct output files")

        # TODO: Detect bug of invalid Cryptomatte state?
        # Detect if any Render Products were set that do not actually exist
        # (e.g. invalid rendervar targets for a renderproduct) because that
        # is what originated the Cryptomatte enable->disable bug.

        if invalid:
            raise PublishValidationError(
                "Invalid Render Settings for Arnold render."
            )


class ValidateUSDRenderCamera(pyblish.api.InstancePlugin):
    """Validate USD Render Settings refer to a valid render camera.

    The render camera is defined in priority by this order:
        1. ROP Node Override Camera Parm (if set)
        2. Render Product Camera (if set - this may differ PER render product!)
        3. Render Settings Camera (if set)

    If None of these are set *or* a currently set entry resolves to an invalid
    camera prim path then we'll report it as an error.

    """

    order = pyblish.api.ValidatorOrder
    families = ["usdrender"]
    hosts = ["houdini"]
    label = "Validate USD Render Camera"
    actions = [SelectROPAction]

    def process(self, instance):

        rop_node = hou.node(instance.data["instance_node"])
        lop_node = instance.data.get("output_node")
        if not lop_node:
            # No valid output node was set. We ignore it since it will
            # be validated by another plug-in.
            return

        stage = lop_node.stage()

        render_settings = get_usd_render_rop_rendersettings(rop_node, stage,
                                                            logger=self.log)
        if not render_settings:
            # Without render settings we basically have no defined
            self.log.error("No render settings found for %s.", rop_node.path())
            return

        render_settings_camera = self._get_camera(render_settings)
        rop_camera = rop_node.evalParm("override_camera")

        invalid = False
        camera_paths = set()
        for render_product in self.iter_render_products(render_settings,
                                                        stage):
            render_product_camera = self._get_camera(render_product)

            # Get first camera path as per order in in this plug-in docstring
            camera_path = next(
                (cam_path for cam_path in [rop_camera,
                                           render_product_camera,
                                           render_settings_camera]
                 if cam_path),
                None
            )
            if not camera_path:
                self.log.error(
                    "No render camera defined for render product: '%s'",
                    render_product.GetPath()
                )
                invalid = True
                continue

            camera_paths.add(camera_path)

        # For the camera paths used across the render products detect
        # whether the path is a valid camera in the stage
        for camera_path in sorted(camera_paths):
            camera_prim = stage.GetPrimAtPath(camera_path)
            if not camera_prim or not camera_prim.IsValid():
                self.log.error(
                    "Render camera path '%s' does not exist in stage.",
                    camera_path
                )
                invalid = True
                continue

            if not camera_prim.IsA(pxr.UsdGeom.Camera):
                self.log.error(
                    "Render camera path '%s' is not a camera.",
                    camera_path
                )
                invalid = True

        if invalid:
            raise PublishValidationError(
                f"No render camera found for {instance.name}.",
                title="Invalid Render Camera",
                description=self.get_description()
            )

    def iter_render_products(self, render_settings, stage):
        for product_path in render_settings.GetProductsRel().GetTargets():
            prim = stage.GetPrimAtPath(product_path)
            if prim.IsA(UsdRender.Product):
                yield UsdRender.Product(prim)

    def _get_camera(self, settings: UsdRender.SettingsBase):
        """Return primary camera target from RenderSettings or RenderProduct"""
        camera_targets = settings.GetCameraRel().GetForwardedTargets()
        if camera_targets:
            return camera_targets[0]

    def get_description(self):
        return inspect.cleandoc(
            """### Missing render camera

            No valid render camera was set for the USD Render Settings.

            The configured render camera path must be a valid camera in the
            stage. Make sure it refers to an existing path and that it is
            a camera.

            """
        )
