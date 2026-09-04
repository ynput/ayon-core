"""Collect custom frame range for render submission."""
from __future__ import annotations

import typing

import pyblish.api

from ayon_core.lib import EnumDef, TextDef
from ayon_core.pipeline import KnownPublishError, get_current_host_name
from ayon_core.pipeline.publish import AYONPyblishPluginMixin

if typing.TYPE_CHECKING:
    from ayon_core.pipeline import CreatedInstance

# For backwards compatibility with deadline's logic
# - Combination of families and host names for which the plugin is compatible.
# - To properly convert the hosts to use the "new way" they have to add
#   "custom.frame.range" family to created instances.
# - We can remove host names from the 'FARM_HOST_NAMES' set once the host
#   integrations are updated to add the family to instances and core has
#   bumped compatibility version for the host.
FARM_FAMILIES = {
    "render", "render.local", "render.farm", "render.frames_farm",
    "prerender", "prerender.farm", "prerender.frames_farm",
    "renderlayer", "imagesequence", "image",
    "vrayscene", "maxrender",
    "arnold_rop", "mantra_rop",
    "karma_rop", "vray_rop", "redshift_rop",
    "renderFarm", "usdrender", "publish.hou",
    "remote_publish_on_farm",
    "deadline"
}
FARM_HOST_NAMES = {
    "aftereffects",
    "blender",
    "celaction",
    "cinema4d",
    "fusion",
    "harmony",
    "houdini",
    "max",
    "maya",
    "nuke",
    "unreal",
}
IS_FARM_HOST = get_current_host_name() in FARM_HOST_NAMES


class CollectCustomFrameRange(
    pyblish.api.InstancePlugin,
    AYONPyblishPluginMixin
):
    """Collect custom frame range for render submission."""

    order = pyblish.api.CollectorOrder + 0.018
    label = "Collect Custom Frame Range"

    # TODO uncomment when all host integrations do add
    #   the 'custom.frame.range' family to instances
    # families = ["custom.frame.range"]

    def process(self, instance: pyblish.api.Instance) -> None:
        if not self._is_compatible_instance(instance):
            return

        attr_values = self.get_attr_values_from_data(instance.data)
        use_custom_frames = attr_values.get("use_custom_frames")
        if not self._is_custom_frames_used(use_custom_frames):
            self.log.debug(
                "Custom frames are not used, "
                "skipping collection of frame range."
            )
            return

        frames = attr_values.get("frames")
        if not frames:
            raise KnownPublishError("Please fill `Custom Frames` value")

        instance.data["customFrames"] = frames
        if use_custom_frames == "reuse_last_version":
            instance.data["reuse_last_version"] = True

    @classmethod
    def get_attr_defs_for_instance(cls, create_context, instance):
        """Get list of attr defs that are set in Settings as artist overridable

        Args:
            create_context (ayon_core.pipeline.create.CreateContext)
            instance (ayon_core.pipeline.create.CreatedInstance):

        Returns:
            (list)
        """
        if not cls._is_compatible_instance(instance):
            return []

        use_custom_frames = (
            cls._get_publish_use_custom_frames_value(instance.data) or "none"
        )

        # explicit frames to render - for test renders
        use_custom_frames_enum_values = [
            {"value": "none", "label": "Disabled"},
            {"value": "custom_only", "label": "Custom Frames Only"},
            {"value": "reuse_last_version", "label": "Reuse from Last Version"}
        ]
        custom_frames_visible = cls._is_custom_frames_used(use_custom_frames)
        return [
            EnumDef(
                "use_custom_frames",
                label="Use Custom Frames",
                default=use_custom_frames,
                items=use_custom_frames_enum_values,
            ),
            TextDef(
                "frames",
                label="Custom Frames",
                default="",
                tooltip="Explicit frames to be rendered. (1001,1003-1004)(2x)",
                visible=custom_frames_visible
            ),
        ]

    @classmethod
    def register_create_context_callbacks(cls, create_context):
        create_context.add_value_changed_callback(cls.on_values_changed)

    @classmethod
    def on_values_changed(cls, event):
        for instance_change in event["changes"]:
            custom_frame_change = cls._get_publish_use_custom_frames_value(
                instance_change["changes"]
            )
            if not custom_frame_change:
                continue

            instance = instance_change["instance"]
            if not cls._is_compatible_instance(instance):
                continue

            new_attrs = cls.get_attr_defs_for_instance(
                event["create_context"], instance
            )
            instance.set_publish_plugin_attr_defs(cls.__name__, new_attrs)

    @classmethod
    def _is_custom_frames_used(cls, value) -> bool:
        return value in ["custom_only", "reuse_last_version"]

    @classmethod
    def _get_publish_use_custom_frames_value(cls, data) -> str | None:
        plugin_data = cls.get_attr_values_from_data_for_plugin(cls, data)
        return plugin_data.get("use_custom_frames")

    @classmethod
    def _is_compatible_instance(
        cls, instance: CreatedInstance | pyblish.api.Instance
    ) -> bool:
        if isinstance(instance, pyblish.api.Instance):
            i_families = instance.data.get("families")
            i_product_base_type = instance.data.get("productBaseType")
        else:
            i_families = instance.get("families")
            i_product_base_type = instance.product_base_type

        # families = [instance.product_base_type]
        families = set()
        if i_families is not None:
            families = set(i_families)

        if "custom.frame.range" in families:
            return True

        if not IS_FARM_HOST:
            return False

        families.add(i_product_base_type)
        return bool(families.intersection(FARM_HOST_NAMES))
