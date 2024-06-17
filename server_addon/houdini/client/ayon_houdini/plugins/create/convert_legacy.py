# -*- coding: utf-8 -*-
"""Converter for legacy Houdini products."""
from ayon_core.pipeline.create.creator_plugins import ProductConvertorPlugin
from ayon_houdini.api.lib import imprint


class HoudiniLegacyConvertor(ProductConvertorPlugin):
    """Find and convert any legacy products in the scene.

    This Converter will find all legacy products in the scene and will
    transform them to the current system. Since the old products doesn't
    retain any information about their original creators, the only mapping
    we can do is based on their families.

    Its limitation is that you can have multiple creators creating product
    name of the same product type and there is no way to handle it. This code
    should nevertheless cover all creators that came with AYON.

    """
    identifier = "io.openpype.creators.houdini.legacy"
    product_type_to_id = {
        "camera": "io.openpype.creators.houdini.camera",
        "ass": "io.openpype.creators.houdini.ass",
        "imagesequence": "io.openpype.creators.houdini.imagesequence",
        "hda": "io.openpype.creators.houdini.hda",
        "pointcache": "io.openpype.creators.houdini.pointcache",
        "redshiftproxy": "io.openpype.creators.houdini.redshiftproxy",
        "redshift_rop": "io.openpype.creators.houdini.redshift_rop",
        "usd": "io.openpype.creators.houdini.usd",
        "usdrender": "io.openpype.creators.houdini.usdrender",
        "vdbcache": "io.openpype.creators.houdini.vdbcache"
    }

    def __init__(self, *args, **kwargs):
        super(HoudiniLegacyConvertor, self).__init__(*args, **kwargs)
        self.legacy_instances = {}

    def find_instances(self):
        """Find legacy products in the scene.

        Legacy products are the ones that doesn't have `creator_identifier`
        parameter on them.

        This is using cached entries done in
        :py:meth:`~HoudiniCreatorBase.cache_instance_data()`

        """
        self.legacy_instances = self.collection_shared_data.get(
            "houdini_cached_legacy_instance")
        if not self.legacy_instances:
            return
        self.add_convertor_item("Found {} incompatible product{}.".format(
            len(self.legacy_instances),
            "s" if len(self.legacy_instances) > 1 else ""
        ))

    def convert(self):
        """Convert all legacy products to current.

        It is enough to add `creator_identifier` and `instance_node`.

        """
        if not self.legacy_instances:
            return

        for product_type, legacy_instances in self.legacy_instances.items():
            if product_type in self.product_type_to_id:
                for instance in legacy_instances:
                    creator_id = self.product_type_to_id[product_type]
                    data = {
                        "creator_identifier": creator_id,
                        "instance_node": instance.path()
                    }
                    if product_type == "pointcache":
                        data["families"] = ["abc"]
                    self.log.info("Converting {} to {}".format(
                        instance.path(), creator_id))
                    imprint(instance, data)
