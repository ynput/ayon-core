"""Collect custom frame range for render submission."""
import pyblish.api
from typing import Optional
from ayon_core.lib import EnumDef, TextDef
from ayon_core.pipeline import KnownPublishError
from ayon_core.pipeline.publish import AYONPyblishPluginMixin


class CollectCustomFrameRange(pyblish.api.InstancePlugin,
                              AYONPyblishPluginMixin):
    """Collect custom frame range for render submission."""

    order = pyblish.api.CollectorOrder + 0.018
    label = "Collect Custom Frame Range"
    families = [
            "render", "render.local", "render.farm", "render.frames_farm",
            "prerender", "prerender.farm", "prerender.frames_farm",
            "renderlayer", "imagesequence", "image",
            "vrayscene", "maxrender",
            "arnold_rop", "mantra_rop",
            "karma_rop", "vray_rop", "redshift_rop",
            "renderFarm", "usdrender", "publish.hou",
            "remote_publish_on_farm",
            "deadline"
    ]

    def process(self, instance: pyblish.api.Instance) -> None:
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
        if not cls.instance_matches_plugin_families(instance):
            return []
        defs = []
        use_custom_frames = (
            cls._get_publish_use_custom_frames_value(instance.data) or "none"
        )

        # explicit frames to render - for test renders
        use_custom_frames_enum_values = [
            {"value": "none", "label": "Disabled"},
            {"value": "custom_only", "label": "Custom Frames Only"},
            {"value": "reuse_last_version", "label": "Reuse from Last Version"}
        ]
        defs.append(
            EnumDef(
                "use_custom_frames",
                label="Use Custom Frames",
                default=use_custom_frames,
                items=use_custom_frames_enum_values,
            )
        )
        custom_frames_visible = cls._is_custom_frames_used(use_custom_frames)
        defs.append(
            TextDef(
                "frames",
                label="Custom Frames",
                default="",
                tooltip="Explicit frames to be rendered. (1001,1003-1004)(2x)",
                visible=custom_frames_visible
            )
        )
        return defs

    @classmethod
    def register_create_context_callbacks(cls, create_context):
        create_context.add_value_changed_callback(cls.on_values_changed)

    @classmethod
    def on_values_changed(cls, event):
        for instance_change in event["changes"]:
            custom_frame_change = cls._get_publish_use_custom_frames_value(
                instance_change["changes"]
            )

            instance = instance_change["instance"]
            # recalculate only if context changes
            if (
                "task" not in instance_change
                and "folderPath" not in instance_change
                and not custom_frame_change
            ):
                continue

            if not cls.instance_matches_plugin_families(instance):
                continue

            new_attrs = cls.get_attr_defs_for_instance(
                event["create_context"], instance
            )
            instance.set_publish_plugin_attr_defs(cls.__name__, new_attrs)

    @classmethod
    def _is_custom_frames_used(cls, value) -> bool:
        return value in ["custom_only", "reuse_last_version"]

    @classmethod
    def _get_publish_use_custom_frames_value(
        cls,
        instance_data
    ) -> Optional[str]:
        return (
            instance_data.get("publish_attributes", {})
                         .get(cls.__name__, {})
                         .get("use_custom_frames")
        )
