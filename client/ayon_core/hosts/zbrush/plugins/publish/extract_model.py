import os
import pyblish.api
from ayon_core.lib import EnumDef
from ayon_core.pipeline import publish
from ayon_core.hosts.zbrush.api.lib import export_tool


class ExtractModel(publish.Extractor):
    """
    Extract PolyMesh(.ma, .fbx, .abc, .obj, .usd) in Zbrush
    """

    order = pyblish.api.ExtractorOrder - 0.05
    label = "Extract Model"
    hosts = ["zbrush"]
    families = ["model"]
    export_format = "obj"

    def process(self, instance):
        attr_values = self.get_attr_values_from_data(instance.data)
        export_format = attr_values.get("exportFormat")
        stagingdir = self.staging_dir(instance)
        filename = f"{instance.name}.{export_format}"
        filepath = os.path.join(stagingdir, filename)

        if "representations" not in instance.data:
            instance.data["representations"] = []

        export_tool(filepath)
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
        defs = super(ExtractModel, cls).get_attribute_defs()
        export_format_enum = ["abc", "fbx", "ma", "obj"]
        defs.extend([
            EnumDef("exportFormat",
                    export_format_enum,
                    default=cls.export_format,
                    label="Export Format Options"),
        ])

        return defs
