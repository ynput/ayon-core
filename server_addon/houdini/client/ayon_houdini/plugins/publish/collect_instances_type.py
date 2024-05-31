"""Collector for different types.

This will add additional families to different instance based on
the creator_identifier parameter.
"""
import pyblish.api


class CollectPointcacheType(pyblish.api.InstancePlugin):
    """Collect data type for different instances."""

    order = pyblish.api.CollectorOrder
    families = ["pointcache", "model"]
    label = "Collect instances types"

    def process(self, instance):
        if instance.data["creator_identifier"] == "io.openpype.creators.houdini.bgeo":  # noqa: E501
            instance.data["families"] += ["bgeo"]
        elif instance.data["creator_identifier"] in {
            "io.openpype.creators.houdini.pointcache",
            "io.openpype.creators.houdini.model"
        }:
            instance.data["families"] += ["abc"]
