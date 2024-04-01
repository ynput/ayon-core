"""Produces instance.data["productGroup"] data used during integration.

Requires:
    dict -> context["anatomyData"] *(pyblish.api.CollectorOrder + 0.49)

Provides:
    instance -> productGroup (str)

"""
import pyblish.api

from ayon_core.lib.profiles_filtering import filter_profiles
from ayon_core.lib import (
    prepare_template_data,
    StringTemplate,
    TemplateUnsolved
)


class IntegrateProductGroup(pyblish.api.InstancePlugin):
    """Integrate Product Group for publish."""

    # Run after CollectAnatomyInstanceData
    order = pyblish.api.IntegratorOrder - 0.1
    label = "Product Group"

    # Attributes set by settings
    product_grouping_profiles = None

    def process(self, instance):
        """Look into product group profiles set by settings.

        Attribute 'product_grouping_profiles' is defined by settings.
        """

        # Skip if 'product_grouping_profiles' is empty
        if not self.product_grouping_profiles:
            return

        if instance.data.get("productGroup"):
            # If productGroup is already set then allow that value to remain
            self.log.debug((
                "Skipping collect product group due to existing value: {}"
            ).format(instance.data["productGroup"]))
            return

        # Skip if there is no matching profile
        filter_criteria = self.get_profile_filter_criteria(instance)
        profile = filter_profiles(
            self.product_grouping_profiles,
            filter_criteria,
            logger=self.log
        )

        if not profile:
            return

        template = profile["template"]
        product_name = instance.data["productName"]
        product_type = instance.data["productType"]

        fill_pairs = prepare_template_data({
            "family": product_type,
            "task": filter_criteria["tasks"],
            "host": filter_criteria["hosts"],
            "subset": product_name,
            "product": {
                "name": product_name,
                "type": product_type,
            },
            "renderlayer": instance.data.get("renderlayer")
        })

        filled_template = None
        try:
            filled_template = StringTemplate.format_strict_template(
                template, fill_pairs
            )
        except (KeyError, TemplateUnsolved):
            keys = fill_pairs.keys()
            self.log.warning((
                "Product grouping failed. Only {} are expected in Settings"
            ).format(','.join(keys)))

        if filled_template:
            instance.data["productGroup"] = filled_template

    def get_profile_filter_criteria(self, instance):
        """Return filter criteria for `filter_profiles`"""
        # TODO: This logic is used in much more plug-ins in one way or another
        #       Maybe better suited for lib?
        # Anatomy data is pre-filled by Collectors
        anatomy_data = instance.data["anatomyData"]

        # Task can be optional in anatomy data
        task = anatomy_data.get("task", {})

        # Return filter criteria
        return {
            "product_types": instance.data["productType"],
            "tasks": task.get("name"),
            "hosts": instance.context.data["hostName"],
            "task_types": task.get("type")
        }
