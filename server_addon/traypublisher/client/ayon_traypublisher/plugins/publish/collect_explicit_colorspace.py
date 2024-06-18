import pyblish.api
from ayon_core.lib import EnumDef
from ayon_core.pipeline import colorspace
from ayon_core.pipeline import publish
from ayon_core.pipeline.publish import KnownPublishError


class CollectColorspace(pyblish.api.InstancePlugin,
                        publish.AYONPyblishPluginMixin,
                        publish.ColormanagedPyblishPluginMixin):
    """Collect explicit user defined representation colorspaces"""

    label = "Choose representation colorspace"
    order = pyblish.api.CollectorOrder + 0.49
    hosts = ["traypublisher"]
    families = ["render", "plate", "reference", "image", "online"]
    enabled = False

    default_colorspace_items = [
        (None, "Don't override")
    ]
    colorspace_items = list(default_colorspace_items)
    colorspace_attr_show = False
    config_items = None

    def process(self, instance):
        values = self.get_attr_values_from_data(instance.data)
        colorspace_value = values.get("colorspace", None)
        if colorspace_value is None:
            return

        color_data = colorspace.convert_colorspace_enumerator_item(
            colorspace_value, self.config_items)

        colorspace_name = self._colorspace_name_by_type(color_data)
        self.log.debug("Explicit colorspace name: {}".format(colorspace_name))

        context = instance.context
        for repre in instance.data.get("representations", {}):
            self.set_representation_colorspace(
                representation=repre,
                context=context,
                colorspace=colorspace_name
            )

    def _colorspace_name_by_type(self, colorspace_data):
        """
        Returns colorspace name by type

        Arguments:
            colorspace_data (dict): colorspace data

        Returns:
            str: colorspace name
        """
        if colorspace_data["type"] == "colorspaces":
            return colorspace_data["name"]
        elif colorspace_data["type"] == "roles":
            return colorspace_data["colorspace"]
        else:
            raise KnownPublishError(
                (
                    "Collecting of colorspace failed. used config is missing "
                    "colorspace type: '{}' . Please contact your pipeline TD."
                ).format(colorspace_data['type'])
            )

    @classmethod
    def apply_settings(cls, project_settings):
        config_data = colorspace.get_current_context_imageio_config_preset(
            project_settings=project_settings
        )

        enabled = False
        colorspace_items = list(cls.default_colorspace_items)
        config_items = None
        if config_data:
            enabled = True
            filepath = config_data["path"]
            config_items = colorspace.get_ocio_config_colorspaces(filepath)
            labeled_colorspaces = colorspace.get_colorspaces_enumerator_items(
                config_items,
                include_aliases=True,
                include_roles=True
            )
            colorspace_items.extend(labeled_colorspaces)

        cls.config_items = config_items
        cls.colorspace_items = colorspace_items
        cls.enabled = enabled

    @classmethod
    def get_attribute_defs(cls):
        return [
            EnumDef(
                "colorspace",
                cls.colorspace_items,
                default="Don't override",
                label="Override Colorspace"
            )
        ]
