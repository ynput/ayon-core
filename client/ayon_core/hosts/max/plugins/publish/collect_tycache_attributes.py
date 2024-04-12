import pyblish.api
import copy


class CollectTyCacheData(pyblish.api.InstancePlugin):
    """Collect Channel Attributes for TyCache Export"""

    order = pyblish.api.CollectorOrder + 0.02
    label = "Collect tyCache attribute Data"
    hosts = ['max']
    families = ["tycache", "tyspline"]

    def process(self, instance):
        family = instance.data["productType"]
        instance.data["exportMode"] = 2 if family == "tycache" else 6
        # product_type = instance.data["tyc_exportMode"]
        # tyc_instance = context.create_instance(tyc_product_name)
        # tyc_instance[:] = instance[:]
        # tyc_instance.data.update(copy.deepcopy(dict(instance.data)))
        # tyc_instance.data["name"] = tyc_product_name
        # tyc_instance.data["label"] = tyc_product_name
        # tyc_instance.data["productName"] = tyc_product_name
        # tyc_instance.data["productType"] = instance.data["tyc_exportMode"]
        # tyc_instance.data["exportMode"] = 2 if family == "tycache" else 6
