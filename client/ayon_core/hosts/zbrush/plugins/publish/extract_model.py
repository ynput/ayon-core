import os
import pyblish.api
from ayon_core.lib import EnumDef
from ayon_core.pipeline import publish
from ayon_core.pipeline.publish import (
    AYONPyblishPluginMixin
)

from ayon_core.hosts.zbrush.api.lib import export_tool


class ExtractModel(publish.Extractor,
                   AYONPyblishPluginMixin):
    """
    Extract PolyMesh(.ma, .fbx, .abc, .obj, .usd) in Zbrush
    """

    order = pyblish.api.ExtractorOrder - 0.05
    label = "Extract Model"
    hosts = ["zbrush"]
    families = ["model"]
    export_format = "obj"

    def process(self, instance):
        creator_attrs = instance.data["creator_attributes"]
        attr_values = self.get_attr_values_from_data(instance.data)
        export_format = attr_values.get("exportFormat")
        stagingdir = self.staging_dir(instance)
        filename = f"{instance.name}.{export_format}"
        filepath = os.path.join(stagingdir, filename)
        subd_level = creator_attrs.get("subd_level")

        if "representations" not in instance.data:
            instance.data["representations"] = []

        export_tool(filepath, subd_level)
        representation = {
            "name": export_format,
            "ext": export_format,
            "files": filename,
            "stagingDir": stagingdir,
        }

        instance.data["representations"].append(representation)
        self.log.info(
            "Extracted instance '%s' to: %s" % (instance.name, filepath)
        )

    @classmethod
    def get_attribute_defs(cls):
        export_format_enum = ["abc", "fbx", "ma", "obj"]
        return[
            EnumDef("exportFormat",
                    export_format_enum,
                    default=cls.export_format,
                    label="Export Format Options")
        ]
