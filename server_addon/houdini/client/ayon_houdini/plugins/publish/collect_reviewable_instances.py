import pyblish.api
from ayon_houdini.api import plugin


class CollectReviewableInstances(plugin.HoudiniInstancePlugin):
    """Collect Reviewable Instances.

    Basically, all instances of the specified families
      with creator_attribure["review"]
    """

    order = pyblish.api.CollectorOrder
    label = "Collect Reviewable Instances"
    families = ["mantra_rop",
                "karma_rop",
                "redshift_rop",
                "arnold_rop",
                "vray_rop"]

    def process(self, instance):
        creator_attribute = instance.data["creator_attributes"]

        instance.data["review"] = creator_attribute.get("review", False)
