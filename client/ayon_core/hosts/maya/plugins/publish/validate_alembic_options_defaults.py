import pyblish.api

from ayon_core.pipeline import OptionalPyblishPluginMixin
from ayon_core.pipeline.publish import RepairAction, PublishValidationError


class ValidateAlembicDefaultsPointcache(
    pyblish.api.InstancePlugin, OptionalPyblishPluginMixin
):
    """Validate the attributes on the instance are defaults.

    The defaults are defined in the project settings.
    """

    order = pyblish.api.ValidatorOrder
    families = ["pointcache"]
    hosts = ["maya"]
    label = "Validate Alembic Options Defaults"
    actions = [RepairAction]
    optional = True

    plugin_name = "ExtractAlembic"

    @classmethod
    def _get_settings(cls, context):
        maya_settings = context.data["project_settings"]["maya"]
        settings = maya_settings["publish"]["ExtractAlembic"]
        return settings

    @classmethod
    def _get_publish_attributes(cls, instance):
        attributes = instance.data["publish_attributes"][
            cls.plugin_name(
                instance.data["publish_attributes"]
            )
        ]

        return attributes

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        settings = self._get_settings(instance.context)

        attributes = self._get_publish_attributes(instance)

        msg = (
            "Alembic Extract setting \"{}\" is not the default value:"
            "\nCurrent: {}"
            "\nDefault Value: {}\n"
        )
        errors = []
        for key, value in attributes.items():
            default_value = settings[key]

            # Lists are best to compared sorted since we cant rely on the order
            # of the items.
            if isinstance(value, list):
                value = sorted(value)
                default_value = sorted(default_value)

            if value != default_value:
                errors.append(msg.format(key, value, default_value))

        if errors:
            raise PublishValidationError("\n".join(errors))

    @classmethod
    def repair(cls, instance):
        # Find create instance twin.
        create_context = instance.context.data["create_context"]
        create_instance = create_context.get_instance_by_id(
            instance.data["instance_id"]
        )

        # Set the settings values on the create context then save to workfile.
        publish_attributes = instance.data["publish_attributes"]
        plugin_name = cls.plugin_name(publish_attributes)
        attributes = cls._get_publish_attributes(instance)
        settings = cls._get_settings(instance.context)
        create_publish_attributes = create_instance.data["publish_attributes"]
        for key in attributes:
            create_publish_attributes[plugin_name][key] = settings[key]

        create_context.save_changes()


class ValidateAlembicDefaultsAnimation(
    ValidateAlembicDefaultsPointcache
):
    """Validate the attributes on the instance are defaults.

    The defaults are defined in the project settings.
    """
    label = "Validate Alembic Options   Defaults"
    families = ["animation"]
    plugin_name = "ExtractAnimation"
