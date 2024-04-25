from pathlib import Path
from pprint import pformat

import pyblish.api
from ayon_core.pipeline import publish
from ayon_core.pipeline import colorspace
from ayon_core.pipeline import get_current_project_name


class CollectColorspaceLook(pyblish.api.InstancePlugin,
                            publish.AYONPyblishPluginMixin):
    """Collect OCIO colorspace look from Tool Group in Resolve's Fusion tab
    """

    label = "Collect Colorspace Look"
    order = pyblish.api.CollectorOrder
    # hosts = ["resolve"]
    families = ["clip"]

    # colorgroup_tool_settings = None

    def process(self, instance):
        timeline_item = instance.data["item"]

        # get fusion comp
        comp_count: int = timeline_item.GetFusionCompCount()
        if comp_count != 1:
            self.log.info("Skipping TimelineItem since no fusion comp was found: {}".format(timeline_item))
            return
        comp = timeline_item.GetFusionCompByIndex(1)

        # get colorgroup tool "AYON_ociolook_GROUP"
        colorgroup_tool = None
        for tool in comp.GetToolList().values():
            if tool.Name == "AYON_ociolook_GROUP":
                colorgroup_tool = tool
        if not colorgroup_tool:
            self.log.info("No colorgroup tool found in comp")
            return

        # get OCIO config data, available colorspaces
        # and initialize ociolook attributes
        project_name = get_current_project_name()
        ocio_config_data = colorspace.get_imageio_config(project_name, "resolve")
        ocio_colorspaces = colorspace.get_ocio_config_colorspaces(ocio_config_data["path"])
        ociolook_attrs = self.build_ociolook_settings(colorgroup_tool, ocio_colorspaces) 

        # prepare LUTfile representation
        lut_repre_name = "LUTfile"
        file_path = Path(ociolook_attrs["abs_lut_path"])
        file_name = file_path.stem
        file_ext = file_path.suffix.strip(".")

        # set output name with base_name which was cleared
        # of all symbols and all parts were capitalized
        output_name = (file_name.replace("_", " ")
                                .replace(".", " ")
                                .replace("-", " ")
                                .title()
                                .replace(" ", ""))

        # create lut representation data
        lut_repre = {
            "name": lut_repre_name,
            "output": output_name,
            "ext": file_ext,
            "files": f"{file_name}.{file_ext}",
            "stagingDir": f"{file_path.parent}",
            "tags": []
        }
        data = instance.data.copy()
        data.update({
            "productName": "Foo",
            "productType": "ociolook",
            "family": "ociolook",
            "families": ["ociolook"],
            "name": "foo" + "_" + data["folderPath"],
            "label": "{} - {}".format(
                data["folderPath"], "foo"
            ),
            "representations": [lut_repre],
            "source": f"{file_path}",
            "ocioLookWorkingSpace": ociolook_attrs["working_colorspace"],
            "ocioLookItems": [
                {
                    "name": lut_repre_name,
                    "ext": file_ext,
                    "input_colorspace": ociolook_attrs["input_colorspace"],
                    "output_colorspace": ociolook_attrs["output_colorspace"],
                    "direction": ociolook_attrs["direction"],
                    "interpolation": ociolook_attrs["interpolation"],
                    "config_data": ocio_colorspaces
                }
            ],
        })
        _instance = instance.context.create_instance(**data)
        self.log.info(f"Created instance {_instance}")
        self.log.debug(f"{_instance.data = }")


        self.log.debug(pformat(instance.data))

    def build_ociolook_settings(self, tool, available_colorspaces) -> dict[str: dict] | None:
        #! would be could if i wrote a parser for fusion tool settings
        settings = tool.SaveSettings()["Tools"][tool.Name]["Tools"]

        # get tools
        lut_tool = settings["LUTfile"]
        in_color_xfm_tool = settings["Input_ColorTransform"]
        out_color_xfm_tool = settings["Output_ColorTransform"]

        # get desired tool settings
        cs_name_input: str = in_color_xfm_tool["Inputs"]["SourceSpace"]["Value"][1]
        cs_name_working: str = in_color_xfm_tool["Inputs"]["OutputSpace"]["Value"][1]
        cs_name_output: str = out_color_xfm_tool["Inputs"]["SourceSpace"]["Value"][1]
        lut_file = Path(lut_tool["Inputs"]["LUTFile"]["Value"])
        if lut_tool["Inputs"].get("Direction"):
            lut_direction = lut_tool["Inputs"]["Direction"]["Value"][1].lower()
        else:
            lut_direction = "forward"
        if lut_tool["Inputs"].get("Interpolation"):
            lut_interpolation = lut_tool["Inputs"]["Interpolation"]["Value"][1].lower()
        else:
            lut_interpolation = "linear"

        # find colorspace data
        input_cs, output_cs, working_cs = None, None, None
        for cs_name, cs_data in available_colorspaces["colorspaces"].items():
            if cs_name == cs_name_input:
                input_cs = cs_data.copy()
                input_cs["name"] = cs_name
                input_cs["type"] = "colorspaces"
            if cs_name == cs_name_output:
                output_cs = cs_data.copy()
                output_cs["name"] = cs_name
                output_cs["type"] = "colorspaces"
            if cs_name == cs_name_working:
                working_cs = cs_data.copy()
                working_cs["name"] = cs_name
                working_cs["type"] = "colorspaces"

        if not all([input_cs, output_cs, working_cs ,lut_file]):
            self.log.error("Colorspace values are missing")
            return None

        result = {
            "abs_lut_path": str(lut_file),
            "direction": lut_direction,
            "interpolation": lut_interpolation,
            "input_colorspace": input_cs,
            "output_colorspace": output_cs,
            "working_colorspace": working_cs,
        }
        self.log.debug(f"ociolook settings = {result}")
        return result
