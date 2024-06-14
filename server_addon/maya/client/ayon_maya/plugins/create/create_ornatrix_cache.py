from ayon_maya.api import (
    lib,
    plugin
)


class CreateOrnatrixCache(plugin.MayaCreator):
    """Output for procedural plugin nodes of Yeti """

    identifier = "io.openpype.creators.maya.ornatrixcache"
    label = "Ornatrix Cache"
    product_type = "ornatrixCache"
    icon = "pagelines"

    def get_instance_attr_defs(self):

        # Add animation data without step and handles
        remove = {"step", "handleStart", "handleEnd"}
        defs = [attr_def for attr_def in lib.collect_animation_defs()
                if attr_def.key not in remove]

        return defs
