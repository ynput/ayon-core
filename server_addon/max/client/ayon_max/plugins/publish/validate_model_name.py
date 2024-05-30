# -*- coding: utf-8 -*-
"""Validate model nodes names."""
import re

import pyblish.api

from ayon_max.api.action import SelectInvalidAction

from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishXmlValidationError,
    ValidateContentsOrder
)

class ValidateModelName(pyblish.api.InstancePlugin,
                        OptionalPyblishPluginMixin):
    """Validate Model Name.

    Validation regex is `(.*)_(?P<subset>.*)_(GEO)` by default.
    The setting supports the following regex group name:
        - project
        - asset
        - subset

    Examples:
    	`{SOME_RANDOM_NAME}_{YOUR_SUBSET_NAME}_GEO` should be your
        default model name.
    	The regex of `(?P<subset>.*)` can be replaced by `(?P<asset>.*)`
    	and `(?P<project>.*)`.
        `(.*)_(?P<asset>.*)_(GEO)` check if your model name is
        `{SOME_RANDOM_NAME}_{CURRENT_ASSET_NAME}_GEO`
        `(.*)_(?P<project>.*)_(GEO)` check if your model name is
        `{SOME_RANDOM_NAME}_{CURRENT_PROJECT_NAME}_GEO`

    """
    optional = True
    order = ValidateContentsOrder
    hosts = ["max"]
    families = ["model"]
    label = "Validate Model Name"
    actions = [SelectInvalidAction]

    settings_category = "max"

    # defined by settings
    regex = r"(.*)_(?P<subset>.*)_(GEO)"
    # cache
    regex_compiled = None

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        invalid = self.get_invalid(instance)
        if invalid:
            names = "\n".join(
                "- {}".format(node.name) for node in invalid
            )
            raise PublishXmlValidationError(
                plugin=self,
                message="Nodes found with invalid model names: {}".format(invalid),
                formatting_data={"nodes": names}
            )

    @classmethod
    def get_invalid(cls, instance):
        if not cls.regex:
            cls.log.warning("No regex pattern set. Nothing to validate.")
            return

        members = instance.data.get("members")
        if not members:
            cls.log.error("No members found in the instance.")
            return

        cls.regex_compiled = re.compile(cls.regex)

        invalid = []
        for obj in members:
            if cls.invalid_name(instance, obj):
                invalid.append(obj)
        return invalid

    @classmethod
    def invalid_name(cls, instance, obj):
        """Function to check the object has invalid name
        regarding to the validation regex in the AYON setttings

        Args:
            instance (pyblish.api.instance): Instance
            obj (str): object name

        Returns:
            str: invalid object
        """
        regex = cls.regex_compiled
        name = obj.name
        match = regex.match(name)

        if match is None:
            cls.log.error("Invalid model name on: %s", name)
            cls.log.error("Name doesn't match regex {}".format(regex.pattern))
            return obj

        # Validate regex groups
        invalid = False
        compare = {
            "project": instance.context.data["projectName"],
            "asset": instance.data["folderPath"],
            "subset": instance.data["productName"]
        }
        for key, required_value in compare.items():
            if key in regex.groupindex:
                if match.group(key) != required_value:
                    cls.log.error(
                        "Invalid %s name for the model %s, "
                        "required name is %s",
                        key, name, required_value
                    )
                    invalid = True

        if invalid:
            return obj
