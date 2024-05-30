import inspect

import pyblish.api
from ayon_core.pipeline import OptionalPyblishPluginMixin
from ayon_core.pipeline.publish import PublishValidationError, RepairAction
from ayon_maya.api import plugin


class ValidateAlembicDefaultsPointcache(
    plugin.MayaInstancePlugin, OptionalPyblishPluginMixin
):
    """Validate the attributes on the instance are defaults.

    The defaults are defined in the project settings.
    """

    order = pyblish.api.ValidatorOrder
    families = ["pointcache"]
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
        return instance.data["publish_attributes"][cls.plugin_name]

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        settings = self._get_settings(instance.context)
        attributes = self._get_publish_attributes(instance)

        invalid = {}
        for key, value in attributes.items():
            if key not in settings:
                # This may occur if attributes have changed over time and an
                # existing instance has older legacy attributes that do not
                # match the current settings definition.
                self.log.warning(
                    "Publish attribute %s not found in Alembic Export "
                    "default settings. Ignoring validation for attribute.",
                    key
                )
                continue

            default_value = settings[key]

            # Lists are best to compared sorted since we can't rely on
            # the order of the items.
            if isinstance(value, list):
                value = sorted(value)
                default_value = sorted(default_value)

            if value != default_value:
                invalid[key] = value, default_value

        if invalid:
            non_defaults = "\n".join(
                f"- {key}: {value} \t(default: {default_value})"
                for key, (value, default_value) in invalid.items()
            )

            raise PublishValidationError(
                "Alembic extract options differ from default values:\n"
                f"{non_defaults}",
                description=self.get_description()
            )

    @staticmethod
    def get_description():
        return inspect.cleandoc(
            """### Alembic Extract settings differ from defaults

            The alembic export options differ from the project default values.

            If this is intentional you can disable this validation by
            disabling **Validate Alembic Options Default**.

            If not you may use the "Repair" action to revert all the options to
            their default values.

            """
        )

    @classmethod
    def repair(cls, instance):
        # Find create instance twin.
        create_context = instance.context.data["create_context"]
        create_instance = create_context.get_instance_by_id(
            instance.data["instance_id"]
        )

        # Set the settings values on the create context then save to workfile.
        settings = cls._get_settings(instance.context)
        attributes = cls._get_publish_attributes(create_instance)
        for key in attributes:
            if key not in settings:
                # This may occur if attributes have changed over time and an
                # existing instance has older legacy attributes that do not
                # match the current settings definition.
                cls.log.warning(
                    "Publish attribute %s not found in Alembic Export "
                    "default settings. Ignoring repair for attribute.",
                    key
                )
                continue
            attributes[key] = settings[key]

        create_context.save_changes()


class ValidateAlembicDefaultsAnimation(
    ValidateAlembicDefaultsPointcache
):
    """Validate the attributes on the instance are defaults.

    The defaults are defined in the project settings.
    """
    label = "Validate Alembic Options Defaults"
    families = ["animation"]
    plugin_name = "ExtractAnimation"
