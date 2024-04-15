import os
from collections import OrderedDict

from maya import cmds

from ayon_core.pipeline import publish
from ayon_core.hosts.maya.api.alembic import extract_alembic
from ayon_core.hosts.maya.api.lib import (
    suspended_refresh,
    maintained_selection,
    iter_visible_nodes_in_range
)
from ayon_core.lib import (
    BoolDef,
    TextDef,
    NumberDef,
    EnumDef,
    UISeparatorDef,
    UILabelDef,
)
from ayon_core.pipeline.publish import AYONPyblishPluginMixin
from ayon_core.pipeline import KnownPublishError


class ExtractAlembic(publish.Extractor, AYONPyblishPluginMixin):
    """Produce an alembic of just point positions and normals.

    Positions and normals, uvs, creases are preserved, but nothing more,
    for plain and predictable point caches.

    Plugin can run locally or remotely (on a farm - if instance is marked with
    "farm" it will be skipped in local processing, but processed on farm)
    """

    label = "Extract Pointcache (Alembic)"
    hosts = ["maya"]
    families = ["pointcache", "model", "vrayproxy.alembic"]
    targets = ["local", "remote"]

    # From settings
    attr = []
    attrPrefix = []
    autoSubd = False
    bake_attributes = []
    bake_attribute_prefixes = []
    dataFormat = "ogawa"
    eulerFilter = False
    melPerFrameCallback = ""
    melPostJobCallback = ""
    overrides = []
    preRoll = False
    preRollStartFrame = 0
    pythonPerFrameCallback = ""
    pythonPostJobCallback = ""
    renderableOnly = False
    stripNamespaces = True
    uvsOnly = False
    uvWrite = False
    userAttr = ""
    userAttrPrefix = ""
    verbose = False
    visibleOnly = False
    wholeFrameGeo = False
    worldSpace = True
    writeColorSets = False
    writeFaceSets = False
    writeNormals = True
    writeUVSets = False
    writeVisibility = False

    def process(self, instance):
        if instance.data.get("farm"):
            self.log.debug("Should be processed on farm, skipping.")
            return

        nodes, roots = self.get_members_and_roots(instance)

        # Collect the start and end including handles
        start = float(instance.data.get("frameStartHandle", 1))
        end = float(instance.data.get("frameEndHandle", 1))

        attribute_values = self.get_attr_values_from_data(
            instance.data
        )

        attrs = [
            attr.strip()
            for attr in attribute_values.get("attr", "").split(";")
            if attr.strip()
        ]
        attrs += instance.data.get("userDefinedAttributes", [])
        attrs += self.bake_attributes
        attrs += ["cbId"]

        attr_prefixes = [
            attr.strip()
            for attr in attribute_values.get("attrPrefix", "").split(";")
            if attr.strip()
        ]
        attr_prefixes += self.bake_attribute_prefixes

        user_attrs = [
            attr.strip()
            for attr in attribute_values.get("userAttr", "").split(";")
            if attr.strip()
        ]

        user_attr_prefixes = [
            attr.strip()
            for attr in attribute_values.get("userAttrPrefix", "").split(";")
            if attr.strip()
        ]

        self.log.debug("Extracting pointcache..")
        dirname = self.staging_dir(instance)

        parent_dir = self.staging_dir(instance)
        filename = "{name}.abc".format(**instance.data)
        path = os.path.join(parent_dir, filename)

        root = None
        if not instance.data.get("includeParentHierarchy", True):
            # Set the root nodes if we don't want to include parents
            # The roots are to be considered the ones that are the actual
            # direct members of the set
            root = roots

        kwargs = {
            "file": path,
            "attr": attrs,
            "attrPrefix": attr_prefixes,
            "userAttr": user_attrs,
            "userAttrPrefix": user_attr_prefixes,
            "dataFormat": attribute_values.get("dataFormat", self.dataFormat),
            "endFrame": end,
            "eulerFilter": attribute_values.get(
                "eulerFilter", self.eulerFilter
            ),
            "preRoll": attribute_values.get("preRoll", self.preRoll),
            "preRollStartFrame": attribute_values.get(
                "preRollStartFrame", self.preRollStartFrame
            ),
            "renderableOnly": attribute_values.get(
                "renderableOnly", self.renderableOnly
            ),
            "root": root,
            "selection": True,
            "startFrame": start,
            "step": instance.data.get(
                "creator_attributes", {}
            ).get("step", 1.0),
            "stripNamespaces": attribute_values.get(
                "stripNamespaces", self.stripNamespaces
            ),
            "uvWrite": attribute_values.get("uvWrite", self.uvWrite),
            "verbose": attribute_values.get("verbose", self.verbose),
            "wholeFrameGeo": attribute_values.get(
                "wholeFrameGeo", self.wholeFrameGeo
            ),
            "worldSpace": attribute_values.get("worldSpace", self.worldSpace),
            "writeColorSets": attribute_values.get(
                "writeColorSets", self.writeColorSets
            ),
            "writeCreases": attribute_values.get(
                "writeCreases", self.writeCreases
            ),
            "writeFaceSets": attribute_values.get(
                "writeFaceSets", self.writeFaceSets
            ),
            "writeUVSets": attribute_values.get(
                "writeUVSets", self.writeUVSets
            ),
            "writeVisibility": attribute_values.get(
                "writeVisibility", self.writeVisibility
            ),
            "autoSubd": attribute_values.get(
                "autoSubd", self.autoSubd
            ),
            "uvsOnly": attribute_values.get(
                "uvsOnly", self.uvsOnly
            ),
            "writeNormals": attribute_values.get(
                "writeNormals", self.writeNormals
            ),
            "melPerFrameCallback": attribute_values.get(
                "melPerFrameCallback", self.melPerFrameCallback
            ),
            "melPostJobCallback": attribute_values.get(
                "melPostJobCallback", self.melPostJobCallback
            ),
            "pythonPerFrameCallback": attribute_values.get(
                "pythonPerFrameCallback", self.pythonPostJobCallback
            ),
            "pythonPostJobCallback": attribute_values.get(
                "pythonPostJobCallback", self.pythonPostJobCallback
            )
        }

        if instance.data.get("visibleOnly", False):
            # If we only want to include nodes that are visible in the frame
            # range then we need to do our own check. Alembic's `visibleOnly`
            # flag does not filter out those that are only hidden on some
            # frames as it counts "animated" or "connected" visibilities as
            # if it's always visible.
            nodes = list(
                iter_visible_nodes_in_range(nodes, start=start, end=end)
            )

        suspend = not instance.data.get("refresh", False)
        with suspended_refresh(suspend=suspend):
            with maintained_selection():
                cmds.select(nodes, noExpand=True)
                self.log.debug(
                    "Running `extract_alembic` with the keyword arguments: "
                    "{}".format(kwargs)
                )
                extract_alembic(**kwargs)

        if "representations" not in instance.data:
            instance.data["representations"] = []

        representation = {
            "name": "abc",
            "ext": "abc",
            "files": filename,
            "stagingDir": dirname
        }
        instance.data["representations"].append(representation)

        if not instance.data.get("stagingDir_persistent", False):
            instance.context.data["cleanupFullPaths"].append(path)

        self.log.debug("Extracted {} to {}".format(instance, dirname))

        # Extract proxy.
        if not instance.data.get("proxy"):
            self.log.debug("No proxy nodes found. Skipping proxy extraction.")
            return

        path = path.replace(".abc", "_proxy.abc")
        kwargs["file"] = path
        if not instance.data.get("includeParentHierarchy", True):
            # Set the root nodes if we don't want to include parents
            # The roots are to be considered the ones that are the actual
            # direct members of the set
            kwargs["root"] = instance.data["proxyRoots"]

        with suspended_refresh(suspend=suspend):
            with maintained_selection():
                cmds.select(instance.data["proxy"])
                extract_alembic(**kwargs)

        representation = {
            "name": "proxy",
            "ext": "abc",
            "files": os.path.basename(path),
            "stagingDir": dirname,
            "outputName": "proxy"
        }
        instance.data["representations"].append(representation)

    def get_members_and_roots(self, instance):
        return instance[:], instance.data.get("setMembers")

    @classmethod
    def get_attribute_defs(cls):
        if not cls.overrides:
            return []

        override_defs = OrderedDict({
            "autoSubd": BoolDef(
                "autoSubd",
                label="Auto Subd",
                default=cls.autoSubd,
                tooltip=(
                    "If this flag is present and the mesh has crease edges, "
                    "crease vertices or holes, the mesh (OPolyMesh) would now "
                    "be written out as an OSubD and crease info will be stored"
                    " in the Alembic  file. Otherwise, creases info won't be "
                    "preserved in Alembic file unless a custom Boolean "
                    "attribute SubDivisionMesh has been added to mesh node and"
                    " its value is true."
                )
            ),
            "eulerFilter": BoolDef(
                "eulerFilter",
                label="Euler Filter",
                default=cls.eulerFilter,
                tooltip="Apply Euler filter while sampling rotations."
            ),
            "renderableOnly": BoolDef(
                "renderableOnly",
                label="Renderable Only",
                default=cls.renderableOnly,
                tooltip="Only export renderable visible shapes."
            ),
            "stripNamespaces": BoolDef(
                "stripNamespaces",
                label="Strip Namespaces",
                default=cls.stripNamespaces,
                tooltip=(
                    "Namespaces will be stripped off of the node before being "
                    "written to Alembic."
                )
            ),
            "uvsOnly": BoolDef(
                "uvsOnly",
                label="UVs Only",
                default=cls.uvsOnly,
                tooltip=(
                    "If this flag is present, only uv data for PolyMesh and "
                    "SubD shapes will be written to the Alembic file."
                )
            ),
            "uvWrite": BoolDef(
                "uvWrite",
                label="UV Write",
                default=cls.uvWrite,
                tooltip=(
                    "Uv data for PolyMesh and SubD shapes will be written to "
                    "the Alembic file."
                )
            ),
            "verbose": BoolDef(
                "verbose",
                label="Verbose",
                default=cls.verbose,
                tooltip="Prints the current frame that is being evaluated."
            ),
            "visibleOnly": BoolDef(
                "visibleOnly",
                label="Visible Only",
                default=cls.visibleOnly,
                tooltip="Only export dag objects visible during frame range."
            ),
            "wholeFrameGeo": BoolDef(
                "wholeFrameGeo",
                label="Whole Frame Geo",
                default=cls.wholeFrameGeo,
                tooltip=(
                    "Data for geometry will only be written out on whole "
                    "frames."
                )
            ),
            "worldSpace": BoolDef(
                "worldSpace",
                label="World Space",
                default=cls.worldSpace,
                tooltip="Any root nodes will be stored in world space."
            ),
            "writeColorSets": BoolDef(
                "writeColorSets",
                label="Write Color Sets",
                default=cls.writeColorSets,
                tooltip="Write vertex colors with the geometry."
            ),
            "writeFaceSets": BoolDef(
                "writeFaceSets",
                label="Write Face Sets",
                default=cls.writeFaceSets,
                tooltip="Write face sets with the geometry."
            ),
            "writeNormals": BoolDef(
                "writeNormals",
                label="Write Normals",
                default=cls.writeNormals,
                tooltip="Write normals with the deforming geometry."
            ),
            "writeUVSets": BoolDef(
                "writeUVSets",
                label="Write UV Sets",
                default=cls.writeUVSets,
                tooltip=(
                    "Write all uv sets on MFnMeshes as vector 2 indexed "
                    "geometry parameters with face varying scope."
                )
            ),
            "writeVisibility": BoolDef(
                "writeVisibility",
                label="Write Visibility",
                default=cls.writeVisibility,
                tooltip=(
                    "Visibility state will be stored in the Alembic file. "
                    "Otherwise everything written out is treated as visible."
                )
            ),
            "preRoll": BoolDef(
                "preRoll",
                label="Pre Roll",
                default=cls.preRoll,
                tooltip="This frame range will not be sampled."
            ),
            "preRollStartFrame": NumberDef(
                "preRollStartFrame",
                label="Pre Roll Start Frame",
                tooltip=(
                    "The frame to start scene evaluation at. This is used"
                    " to set the starting frame for time dependent "
                    "translations and can be used to evaluate run-up that"
                    " isn't actually translated."
                ),
                default=cls.preRollStartFrame
            ),
            "dataFormat": EnumDef(
                "dataFormat",
                label="Data Format",
                items=["ogawa", "HDF"],
                default=cls.dataFormat,
                tooltip="The data format to use to write the file."
            ),
            "attr": TextDef(
                "attr",
                label="Custom Attributes",
                placeholder="attr1; attr2; ...",
                default=cls.attr,
                tooltip=(
                    "Attributes matching by name will be included in the "
                    "Alembic export. Attributes should be separated by "
                    "semi-colon `;`"
                )
            ),
            "attrPrefix": TextDef(
                "attrPrefix",
                label="Custom Attributes Prefix",
                placeholder="prefix1; prefix2; ...",
                default=cls.attrPrefix,
                tooltip=(
                    "Attributes starting with these prefixes will be included "
                    "in the Alembic export. Attributes should be separated by "
                    "semi-colon `;`"
                )
            ),
            "userAttr": TextDef(
                "userAttr",
                label="User Attr",
                placeholder="attr1; attr2; ...",
                default=cls.userAttr,
                tooltip=(
                    "Attributes matching by name will be included in the "
                    "Alembic export. Attributes should be separated by "
                    "semi-colon `;`"
                )
            ),
            "userAttrPrefix": TextDef(
                "userAttrPrefix",
                label="User Attr Prefix",
                placeholder="prefix1; prefix2; ...",
                default=cls.userAttrPrefix,
                tooltip=(
                    "Attributes starting with these prefixes will be included "
                    "in the Alembic export. Attributes should be separated by "
                    "semi-colon `;`"
                )
            ),
            "melPerFrameCallback": TextDef(
                "melPerFrameCallback",
                label="Mel Per Frame Callback",
                default=cls.melPerFrameCallback,
                tooltip=(
                    "When each frame (and the static frame) is evaluated the "
                    "string specified is evaluated as a Mel command."
                )
            ),
            "melPostJobCallback": TextDef(
                "melPostJobCallback",
                label="Mel Post Job Callback",
                default=cls.melPostJobCallback,
                tooltip=(
                    "When the translation has finished the string specified "
                    "is evaluated as a Mel command."
                )
            ),
            "pythonPerFrameCallback": TextDef(
                "pythonPerFrameCallback",
                label="Python Per Frame Callback",
                default=cls.pythonPerFrameCallback,
                tooltip=(
                    "When each frame (and the static frame) is evaluated the "
                    "string specified is evaluated as a python command."
                )
            ),
            "pythonPostJobCallback": TextDef(
                "pythonPostJobCallback",
                label="Python Post Frame Callback",
                default=cls.pythonPostJobCallback,
                tooltip=(
                    "When the translation has finished the string specified "
                    "is evaluated as a python command."
                )
            )
        })

        defs = super(ExtractAlembic, cls).get_attribute_defs()

        defs.extend([
            UISeparatorDef("sep_alembic_options"),
            UILabelDef("Alembic Options"),
        ])

        # The Arguments that can be modified by the Publisher
        overrides = set(cls.overrides)
        for key, value in override_defs.items():
            if key not in overrides:
                continue

            defs.append(value)

        defs.append(
            UISeparatorDef("sep_alembic_options_end")
        )

        return defs


class ExtractAnimation(ExtractAlembic):
    label = "Extract Animation (Alembic)"
    families = ["animation"]

    def get_members_and_roots(self, instance):
        # Collect the out set nodes
        out_sets = [node for node in instance if node.endswith("out_SET")]
        if len(out_sets) != 1:
            raise KnownPublishError(
                "Couldn't find exactly one out_SET: {0}".format(out_sets)
            )
        out_set = out_sets[0]
        roots = cmds.sets(out_set, query=True) or []

        # Include all descendants
        nodes = roots
        nodes += cmds.listRelatives(
            roots, allDescendents=True, fullPath=True
        ) or []

        return nodes, roots
