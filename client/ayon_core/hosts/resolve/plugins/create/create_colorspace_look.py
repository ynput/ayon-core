# -*- coding: utf-8 -*-
"""Creator of colorspace look files.

This creator is used to publish colorspace look files
based on pickled fusion tool group settings.
"""
import time
from pathlib import Path
import pickle
from ayon_core.hosts.resolve.api import plugin


TOOLGROUP_TEMPLATE = Path(__file__).parent / "resources" / "ociolook_template.toolgroup"


class CreateColorspaceLook(plugin.Creator):
    """Creates colorspace look Tool Group in Fusion tab."""

    label = "Create Colorspace Look"
    description = "Publishes color space look file."
    product_type = "ociolook"
    defaults = ["Main"]
    icon = "film"
    # enabled = False

    ociolook_tool_settings = None

    def process(self):
        pstart = time.time()
        if not self.selected:
            raise Exception("No timeline items selected. Make the choco.")

        for container in self.selected:
            ti = container["clip"]["item"]

            # get or create fusion comp
            if ti.GetFusionCompCount() == 0:
                comp = ti.AddFusionComp()
            else:
                comp = ti.GetFusionCompByIndex(1)

            # find existing managed groups
            tools = comp.GetToolList().values()
            ociolook_group, effects_group = None, None
            for tool in tools:
                if tool.Name == "AYON_ociolook_GROUP":
                    ociolook_group = tool
                if tool.Name == "AYON_effects_GROUP":
                    effects_group = tool

            # create ociolook group
            if not ociolook_group:
                if not self.ociolook_tool_settings:
                    with TOOLGROUP_TEMPLATE.open("rb") as f:
                        self.ociolook_tool_settings = pickle.load(f)
                self.log.debug(f"{self.ociolook_tool_settings = }")
                pasted = comp.Paste(self.ociolook_tool_settings)
                if not pasted:
                    self.log.err(f"Failed to paste Group {self.ociolook_tool_settings}")

        dur = pstart - time.time()
        self.log.warning(f"Duration: {dur:.2f}s")
