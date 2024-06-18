from ayon_maya.api import (
    lib,
    plugin
)
from ayon_core.lib import BoolDef, NumberDef


class CreateOxCache(plugin.MayaCreator):
    """Output for procedural plugin nodes of Ornatrix """

    identifier = "io.openpype.creators.maya.OxCache"
    label = "Ornatrix Cache"
    product_type = "OxCache"
    icon = "pagelines"

    def get_instance_attr_defs(self):

        # Add animation data without step and handles
        remove = {"handleStart", "handleEnd"}
        defs = [attr_def for attr_def in lib.collect_animation_defs()
                if attr_def.key not in remove]
        defs.extend(
            [
                BoolDef("renderVersion",
                        label="Use Render Version",
                        default=True),
                BoolDef("upDirection",
                        label="Up Direction",
                        default=True),
                BoolDef("useWorldCoordinates",
                        label="Use World Coordinates",
                        default=False),
                BoolDef("exportStrandData",
                        label="Export Strand Data",
                        default=True),
                BoolDef("exportSurfacePositions",
                        label="Export Surface Positions",
                        default=False),
                BoolDef("oneObjectPerFile",
                        label="One Object Per File",
                        default=False),
                BoolDef("exportStrandIds",
                        label="Export Strand Ids",
                        default=True),
                BoolDef("exportStrandGroups",
                        label="Export Strand Groups",
                        default=True),
                BoolDef("exportWidths",
                        label="Export Widths",
                        default=True),
                BoolDef("exportTextureCoordinates",
                        label="Export Texture Coordinates",
                        default=True),
                BoolDef("exportVelocities",
                        label="Export Velocities",
                        default=False),
                BoolDef("exportNormals",
                        label="Export Normals",
                        default=False),
                BoolDef("velocityIntervalCenter",
                        label="Velocity Interval Center",
                        default=False),
                NumberDef("velocityIntervalLength",
                        label="Velocity Interval Length",
                        default=0.5),
                BoolDef("unrealEngineExport",
                        label="Unreal Engine Export",
                        default=False),
                BoolDef("exportEachStrandAsSeparateObject",
                        label="Export Each Strand As Separate Object",
                        default=False)
            ]
        )

        return defs
