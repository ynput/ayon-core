import pyblish.api

from ayon_core.lib import EnumDef
from ayon_core.pipeline.publish import AYONPyblishPluginMixin


class CollectVersionTags(
    pyblish.api.InstancePlugin,
    AYONPyblishPluginMixin
):
    """Collect Version Tags

    Provides a selectable list of tags for the user. Selected tags are stored
     in the instance metadata and applied to the Version Entity during
     integration.
    """

    order = pyblish.api.CollectorOrder + 0.499
    label = "Collect Version Tags"
    settings_category = "core"

    enabled = False

    def process(self, instance):

        attr_values = self.get_attr_values_from_data(instance.data)
        version_tags: list[str] = attr_values.get("version_tags", [])

        if not version_tags:
            return

        self.log.debug(f"Adding tags: {version_tags}")
        tags = instance.data.get("versionTags")
        if tags is None:
            tags = set()
        elif not isinstance(tags, set):
            tags = set(tags)

        tags.update(version_tags)
        instance.data["versionTags"] = tags
        self.log.debug(f"Collected version tags: {tags}")

    @classmethod
    def get_attr_defs_for_instance(cls, create_context, instance):
        project_entity = create_context.get_current_project_entity()
        items = [tag["name"] for tag in project_entity["tags"]]
        if not items:
            plugin_attributes = instance.publish_attributes.get(cls.__name__)
            if plugin_attributes is not None:
                plugin_attributes.pop("version_tags", None)
            return []

        return [
            EnumDef(
                "version_tags",
                label="Version Tags",
                multiselection=True,
                items=items,
                tooltip="Set these tags to versions",
            )
        ]
