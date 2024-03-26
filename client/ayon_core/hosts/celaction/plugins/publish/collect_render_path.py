import os
import pyblish.api
import copy


class CollectRenderPath(pyblish.api.InstancePlugin):
    """Generate file and directory path where rendered images will be"""

    label = "Collect Render Path"
    order = pyblish.api.CollectorOrder + 0.495
    families = ["render.farm"]

    # Presets
    output_extension = "png"
    anatomy_template_key_render_files = None
    anatomy_template_key_metadata = None

    def process(self, instance):
        anatomy = instance.context.data["anatomy"]
        anatomy_data = copy.deepcopy(instance.data["anatomyData"])
        padding = anatomy.templates_obj.frame_padding
        product_type = "render"
        anatomy_data.update({
            "frame": f"%0{padding}d",
            "family": product_type,
            "representation": self.output_extension,
            "ext": self.output_extension
        })
        anatomy_data["product"]["type"] = product_type

        # get anatomy rendering keys
        r_anatomy_key = self.anatomy_template_key_render_files
        m_anatomy_key = self.anatomy_template_key_metadata

        # get folder and path for rendering images from celaction
        r_template_item = anatomy.get_template_item("publish", r_anatomy_key)
        render_dir = r_template_item["directory"].format_strict(anatomy_data)
        render_path = r_template_item["path"].format_strict(anatomy_data)
        self.log.debug("__ render_path: `{}`".format(render_path))

        # create dir if it doesnt exists
        try:
            if not os.path.isdir(render_dir):
                os.makedirs(render_dir, exist_ok=True)
        except OSError:
            # directory is not available
            self.log.warning("Path is unreachable: `{}`".format(render_dir))

        # add rendering path to instance data
        instance.data["path"] = render_path

        # get anatomy for published renders folder path
        m_template_item = anatomy.get_template_item(
            "publish", m_anatomy_key, default=None
        )
        if m_template_item is not None:
            metadata_path = m_template_item["directory"].format_strict(
                anatomy_data
            )
            instance.data["publishRenderMetadataFolder"] = metadata_path
            self.log.info("Metadata render path: `{}`".format(metadata_path))

        self.log.info(f"Render output path set to: `{render_path}`")
