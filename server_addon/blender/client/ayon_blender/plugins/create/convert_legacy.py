# -*- coding: utf-8 -*-
"""Converter for legacy Houdini products."""
from ayon_core.pipeline.create.creator_plugins import ProductConvertorPlugin
from ayon_blender.api.lib import imprint


class BlenderLegacyConvertor(ProductConvertorPlugin):
    """Find and convert any legacy products in the scene.

    This Converter will find all legacy products in the scene and will
    transform them to the current system. Since the old products doesn't
    retain any information about their original creators, the only mapping
    we can do is based on their product types.

    Its limitation is that you can have multiple creators creating product
    of the same product type and there is no way to handle it. This code
    should nevertheless cover all creators that came with OpenPype.

    """
    identifier = "io.openpype.creators.blender.legacy"
    product_type_to_id = {
        "action": "io.openpype.creators.blender.action",
        "camera": "io.openpype.creators.blender.camera",
        "animation": "io.openpype.creators.blender.animation",
        "blendScene": "io.openpype.creators.blender.blendscene",
        "layout": "io.openpype.creators.blender.layout",
        "model": "io.openpype.creators.blender.model",
        "pointcache": "io.openpype.creators.blender.pointcache",
        "render": "io.openpype.creators.blender.render",
        "review": "io.openpype.creators.blender.review",
        "rig": "io.openpype.creators.blender.rig",
    }

    def __init__(self, *args, **kwargs):
        super(BlenderLegacyConvertor, self).__init__(*args, **kwargs)
        self.legacy_instances = {}

    def find_instances(self):
        """Find legacy products in the scene.

        Legacy products are the ones that doesn't have `creator_identifier`
        parameter on them.

        This is using cached entries done in
        :py:meth:`~BlenderCreator.cache_instance_data()`

        """
        self.legacy_instances = self.collection_shared_data.get(
            "blender_cached_legacy_instances")
        if not self.legacy_instances:
            return
        self.add_convertor_item(
            "Found {} incompatible product{}".format(
                len(self.legacy_instances),
                "s" if len(self.legacy_instances) > 1 else ""
            )
        )

    def convert(self):
        """Convert all legacy products to current.

        It is enough to add `creator_identifier` and `instance_node`.

        """
        if not self.legacy_instances:
            return

        for product_type, instance_nodes in self.legacy_instances.items():
            if product_type in self.product_type_to_id:
                for instance_node in instance_nodes:
                    creator_identifier = self.product_type_to_id[product_type]
                    self.log.info(
                        "Converting {} to {}".format(instance_node.name,
                                                     creator_identifier)
                    )
                    imprint(instance_node, data={
                        "creator_identifier": creator_identifier
                    })
