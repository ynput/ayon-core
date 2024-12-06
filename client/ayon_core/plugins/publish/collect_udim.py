"""Publish UDIM tiles."""
import re

import pyblish.api
from ayon_core.lib import BoolDef
from ayon_core.pipeline import publish

UDIM_REGEX = re.compile(r"(.*)\.(?P<udim>\d{4})\.(.*)")


class CollectUDIMs(
    pyblish.api.InstancePlugin, publish.AYONPyblishPluginMixin):
    """Collect UDIMs tiles."""

    label = "Collect UDIMs"
    order = pyblish.api.CollectorOrder + 0.499
    families = ["image"]

    def process(self, instance):
        # type: (pyblish.api.Instance) -> None
        instance_settings = self.get_attr_values_from_data(instance.data)
        is_udim = instance_settings.get("isUDIM", False)
        if not is_udim:
            return

        for representation in instance.data["representations"]:
            if isinstance(representation["files"], (list, tuple)):
                continue

            # sourcery skip: use-named-expression
            match = re.search(UDIM_REGEX, representation["files"])
            if match:
                representation["udim"] = [match.group("udim")]

    @classmethod
    def get_attribute_defs(cls):
        return [
            BoolDef("isUDIM",
                    label="Is UDIM",
                    default=False)
        ]
