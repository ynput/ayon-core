# -*- coding: utf-8 -*-
"""Creator plugin for creating camera."""
import os
from ayon_max.api import plugin
from ayon_core.lib import BoolDef
from ayon_max.api.lib_rendersettings import RenderSettings


class CreateRender(plugin.MaxCreator):
    """Creator plugin for Renders."""
    identifier = "io.openpype.creators.max.render"
    label = "Render"
    product_type = "maxrender"
    icon = "gear"

    settings_category = "max"

    def create(self, product_name, instance_data, pre_create_data):
        from pymxs import runtime as rt
        file = rt.maxFileName
        filename, _ = os.path.splitext(file)
        instance_data["AssetName"] = filename
        instance_data["multiCamera"] = pre_create_data.get("multi_cam")
        num_of_renderlayer = rt.batchRenderMgr.numViews
        if num_of_renderlayer > 0:
            rt.batchRenderMgr.DeleteView(num_of_renderlayer)

        instance = super(CreateRender, self).create(
            product_name,
            instance_data,
            pre_create_data)

        container_name = instance.data.get("instance_node")
        # set output paths for rendering(mandatory for deadline)
        RenderSettings().render_output(container_name)
        # TODO: create multiple camera options
        if self.selected_nodes:
            selected_nodes_name = []
            for sel in self.selected_nodes:
                name = sel.name
                selected_nodes_name.append(name)
            RenderSettings().batch_render_layer(
                container_name, filename,
                selected_nodes_name)

    def get_pre_create_attr_defs(self):
        attrs = super(CreateRender, self).get_pre_create_attr_defs()
        return attrs + [
            BoolDef("multi_cam",
                    label="Multiple Cameras Submission",
                    default=False),
        ]
