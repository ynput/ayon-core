import pyblish.api
from ayon_core.lib import EnumDef
from ayon_core.pipeline import colorspace
from ayon_core.pipeline import publish
from ayon_core.pipeline.publish import PublishError


class CollectExplicitResolution(
    pyblish.api.InstancePlugin,
    publish.AYONPyblishPluginMixin
):
    """Collect explicit user defined resolution attributes for instances"""

    label = "Choose Explicit Resolution"
    order = pyblish.api.CollectorOrder + 0.49
    settings_category = "core"

    enabled = False

    default_resolution_item = (None, "Don't override")
    # Settings
    product_types = []
    options = []

    # caching resoluton items
    resolution_items = None

    def process(self, instance):
        """Process the instance and collect explicit resolution attributes"""

        # Get the values from the instance data
        values = self.get_attr_values_from_data(instance.data)
        resolution_value = values.get("explicit_resolution", None)
        if resolution_value is None:
            return

        # Get the width, height and pixel_aspect from the resolution value
        resolution_data = self._get_resolution_values(resolution_value)

        # Set the values to the instance data
        instance.data.update(resolution_data)

    def _get_resolution_values(self, resolution_value):
        """
        Returns width, height and pixel_aspect from the resolution value

        Arguments:
            resolution_value (str): resolution value

        Returns:
            dict: dictionary with width, height and pixel_aspect
        """
        resolution_items = self._get_resolution_items()
        item_values = None
        # check if resolution_value is in cached items
        if resolution_value in resolution_items:
            item_values = resolution_items[resolution_value]

        if item_values:
            # if the item is in the cache, get the values from it
            return {
                "resolutionWidth": item_values["width"],
                "resolutionHeight": item_values["height"],
                "pixelAspect": item_values["pixel_aspect"]
            }
        else:
            raise PublishError(
                f"Invalid resolution value: {resolution_value}")

    @classmethod
    def _get_resolution_items(cls):
        if cls.resolution_items is None:
            resolution_items = {}
            for item in cls.options:
                item_text = f"{item['width']}x{item['height']}x{item['pixel_aspect']}"
                resolution_items[item_text] = item

            cls.resolution_items = resolution_items

        return cls.resolution_items

    @classmethod
    def get_attr_defs_for_instance(
        cls, create_context, instance
    ):
        if instance.product_type not in cls.product_types:
            return []

        # Get the resolution items
        resolution_items = cls._get_resolution_items()

        items = [cls.default_resolution_item]
        # Add all cached resolution items to the dropdown options
        for item_text in resolution_items:
            items.append((item_text, item_text))

        return [
            EnumDef(
                "explicit_resolution",
                items,
                default="Don't override",
                label="Override Resolution"
            )
        ]
