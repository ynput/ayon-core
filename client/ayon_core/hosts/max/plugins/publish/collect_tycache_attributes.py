import pyblish.api
import copy
from pymxs import runtime as rt


class CollectTyFlowData(pyblish.api.InstancePlugin):
    """Collect Channel Attributes for TyCache Export"""

    order = pyblish.api.CollectorOrder + 0.02
    label = "Collect tyCache attribute Data"
    hosts = ['max']
    families = ["tyflow"]

    def process(self, instance):
        context = instance.context
        family = instance.data["productType"]
        instance.data["exportMode"] = 2 if family == "tycache" else 6
        container = rt.GetNodeByName(instance.data["instance_node"])
        tyc_product_names = [
                name for name
                in container.modifiers[0].AYONTyCacheData.tyc_handles
        ]
        # TODO: need to do regex when the export particle has some names without regex.
        for tyc_product_name in tyc_product_names:
            tyc_instance = context.create_instance(tyc_product_name)
            tyc_instance[:] = instance[:]
            tyc_instance.data.update(copy.deepcopy(dict(instance.data)))
            tyc_instance.data["name"] = tyc_product_name
            tyc_instance.data["label"] = tyc_product_name
            tyc_instance.data["productName"] = tyc_product_name
            tyc_instance.data["productType"] = instance.data["tyc_exportMode"]
            tyc_instance.data["exportMode"] = 2 if family == "tycache" else 6
            tyc_instance.data["families"] = [instance.data["tyc_exportMode"]]
            instance.data.update(tyc_instance.data)