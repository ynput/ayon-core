import pyblish.api
import re
import copy
from ayon_core.lib import BoolDef
from ayon_core.pipeline.publish import AYONPyblishPluginMixin
from ayon_core.hosts.max.api.lib import get_tyflow_export_operators
from pymxs import runtime as rt


class CollectTyFlowData(pyblish.api.InstancePlugin,
                        AYONPyblishPluginMixin):
    """Collect Channel Attributes for TyCache Export"""

    order = pyblish.api.CollectorOrder + 0.005
    label = "Collect tyCache attribute Data"
    hosts = ['max']
    families = ["tyflow"]
    validate_tycache_frame_range = True

    @classmethod
    def apply_settings(cls, project_settings):

        settings = (
            project_settings["max"]["publish"]["ValidateTyCacheFrameRange"]
        )
        cls.validate_tycache_frame_range = settings["active"]

    def process(self, instance):
        context = instance.context
        container_name = instance.data["instance_node"]
        container = rt.GetNodeByName(container_name)
        tyc_product_names = [
            name for name
            in container.modifiers[0].AYONTyCacheData.tyc_exports
        ]
        attr_values = self.get_attr_values_from_data(instance.data)
        for tyc_product_name in tyc_product_names:
            self.log.debug(f"Creating instance for operator:{tyc_product_name}")
            tyc_instance = context.create_instance(tyc_product_name)
            tyc_instance[:] = instance[:]
            tyc_instance.data.update(copy.deepcopy(dict(instance.data)))
            # Replace all runs of whitespace with underscore
            prod_name = re.sub(r"\s+", "_", tyc_product_name)
            operator = next((node for node in get_tyflow_export_operators()
                             if node.name == tyc_product_name), None)   # noqa
            product_type = "tycache" if operator.exportMode == 2 else "tyspline"
            tyc_instance.data.update({
                "name": f"{container_name}_{prod_name}",
                "label": f"{container_name}_{prod_name}",
                "family": product_type,
                "families": [product_type],
                "productName": f"{container_name}_{prod_name}",
                # get the name of operator for the export
                "operator": operator,
                "exportMode": operator.exportMode,
                "material_cache": attr_values.get("material"),
                "productType": product_type,
                "creator_identifier": (
                    f"io.openpype.creators.max.{product_type}"),
                "publish_attributes": {
                    "ValidateTyCacheFrameRange": {
                        "active": attr_values.get("has_frame_range_validator")}
                }
            })
            instance.append(tyc_instance)

    @classmethod
    def get_attribute_defs(cls):
        return [
            BoolDef("has_frame_range_validator",
                    label="Validate TyCache Frame Range",
                    default=cls.validate_tycache_frame_range),
            BoolDef("material",
                    label="Publish along with Material",
                    default=True)
        ]