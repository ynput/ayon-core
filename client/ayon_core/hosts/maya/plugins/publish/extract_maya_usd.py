import os
import six
import json
import contextlib

from maya import cmds
import maya.api.OpenMaya as om

from ayon_core.pipeline import publish
from ayon_core.lib import BoolDef
from ayon_core.hosts.maya.api.lib import maintained_selection, maintained_time


def parse_version(version_str):
    """Parse string like '0.26.0' to (0, 26, 0)"""
    return tuple(int(v) for v in version_str.split("."))


def get_node_hash(node):
    """Return integer MObjectHandle hash code.

    Arguments:
        node (str): Maya node path.

    Returns:
        int: MObjectHandle.hashCode()

    """
    sel = om.MSelectionList()
    sel.add(node)
    return om.MObjectHandle(sel.getDependNode(0)).hashCode()


@contextlib.contextmanager
def usd_export_attributes(nodes, attrs=None, attr_prefixes=None, mapping=None):
    """Define attributes for the given nodes that should be exported.

    MayaUSDExport will export custom attributes if the Maya node has a
    string attribute `USD_UserExportedAttributesJson` that provides an
    export mapping for the maya attributes. This context manager will try
    to autogenerate such an attribute during the export to include attributes
    for the export.

    Arguments:
        nodes (List[str]): Nodes to process.
        attrs (Optional[List[str]]): Full name of attributes to include.
        attr_prefixes (Optional[List[str]]): Prefixes of attributes to include.
        mapping (Optional[Dict[Dict]]): A mapping per attribute name for the
            conversion to a USD attribute, including renaming, defining type,
            converting attribute precision, etc. This match the usual
            `USD_UserExportedAttributesJson` json mapping of `mayaUSDExport`.
            When no mapping provided for an attribute it will use `{}` as
            value.

    Examples:
          >>> with usd_export_attributes(
          >>>     ["pCube1"], attrs="myDoubleAttributeAsFloat", mapping={
          >>>         "myDoubleAttributeAsFloat": {
          >>>           "usdAttrName": "my:namespace:attrib",
          >>>           "translateMayaDoubleToUsdSinglePrecision": True,
          >>>         }
          >>> })

    """
    # todo: this might be better done with a custom export chaser
    #   see `chaser` argument for `mayaUSDExport`

    if not attrs and not attr_prefixes:
        # context manager does nothing
        yield
        return

    if attrs is None:
        attrs = []
    if attr_prefixes is None:
        attr_prefixes = []
    if mapping is None:
        mapping = {}

    usd_json_attr = "USD_UserExportedAttributesJson"
    strings = attrs + ["{}*".format(prefix) for prefix in attr_prefixes]
    context_state = {}

    # Keep track of the processed nodes as a node might appear more than once
    # e.g. when there are instances.
    processed = set()
    for node in set(nodes):
        node_attrs = cmds.listAttr(node, st=strings)
        if not node_attrs:
            # Nothing to do for this node
            continue

        hash_code = get_node_hash(node)
        if hash_code in processed:
            continue

        node_attr_data = {}
        for node_attr in set(node_attrs):
            node_attr_data[node_attr] = mapping.get(node_attr, {})
        if cmds.attributeQuery(usd_json_attr, node=node, exists=True):
            existing_node_attr_value = cmds.getAttr(
                "{}.{}".format(node, usd_json_attr)
            )
            if existing_node_attr_value and existing_node_attr_value != "{}":
                # Any existing attribute mappings in an existing
                # `USD_UserExportedAttributesJson` attribute always take
                # precedence over what this function tries to imprint
                existing_node_attr_data = json.loads(existing_node_attr_value)
                node_attr_data.update(existing_node_attr_data)

        processed.add(hash_code)
        context_state[node] = json.dumps(node_attr_data)

    sel = om.MSelectionList()
    dg_mod = om.MDGModifier()
    fn_string = om.MFnStringData()
    fn_typed = om.MFnTypedAttribute()
    try:
        for node, value in context_state.items():
            data = fn_string.create(value)
            sel.clear()
            if cmds.attributeQuery(usd_json_attr, node=node, exists=True):
                # Set the attribute value
                sel.add("{}.{}".format(node, usd_json_attr))
                plug = sel.getPlug(0)
                dg_mod.newPlugValue(plug, data)
            else:
                # Create attribute with the value as default value
                sel.add(node)
                node_obj = sel.getDependNode(0)
                attr_obj = fn_typed.create(usd_json_attr,
                                           usd_json_attr,
                                           om.MFnData.kString,
                                           data)
                dg_mod.addAttribute(node_obj, attr_obj)
        dg_mod.doIt()
        yield
    finally:
        dg_mod.undoIt()


class ExtractMayaUsd(publish.Extractor,
                     publish.OptionalPyblishPluginMixin):
    """Extractor for Maya USD Asset data.

    Upon publish a .usd (or .usdz) asset file will typically be written.
    """

    label = "Extract Maya USD Asset"
    hosts = ["maya"]
    families = ["mayaUsd"]

    @property
    def options(self):
        """Overridable options for Maya USD Export

        Given in the following format
            - {NAME: EXPECTED TYPE}

        If the overridden option's type does not match,
        the option is not included and a warning is logged.

        """

        # TODO: Support more `mayaUSDExport` parameters
        return {
            "defaultUSDFormat": str,
            "stripNamespaces": bool,
            "mergeTransformAndShape": bool,
            "exportDisplayColor": bool,
            "exportColorSets": bool,
            "exportInstances": bool,
            "exportUVs": bool,
            "exportVisibility": bool,
            "exportComponentTags": bool,
            "exportRefsAsInstanceable": bool,
            "eulerFilter": bool,
            "renderableOnly": bool,
            "convertMaterialsTo": str,
            "shadingMode": (str, None),  # optional str
            "jobContext": (list, None),  # optional list
            "filterTypes": (list, None),  # optional list
            "staticSingleSample": bool
            # "worldspace": bool,
        }

    @property
    def default_options(self):
        """The default options for Maya USD Export."""

        # TODO: Support more `mayaUSDExport` parameters
        return {
            "defaultUSDFormat": "usdc",
            "stripNamespaces": False,
            "mergeTransformAndShape": True,
            "exportDisplayColor": False,
            "exportColorSets": True,
            "exportInstances": True,
            "exportUVs": True,
            "exportVisibility": True,
            "exportComponentTags": False,
            "exportRefsAsInstanceable": False,
            "eulerFilter": True,
            "renderableOnly": False,
            "shadingMode": "none",
            "convertMaterialsTo": "none",
            "jobContext": None,
            "filterTypes": None,
            "staticSingleSample": True
            # "worldspace": False
        }

    def parse_overrides(self, instance, options):
        """Inspect data of instance to determine overridden options"""

        for key in instance.data:
            if key not in self.options:
                continue

            # Ensure the data is of correct type
            value = instance.data[key]
            if isinstance(value, six.text_type):
                value = str(value)
            if not isinstance(value, self.options[key]):
                self.log.warning(
                    "Overridden attribute {key} was of "
                    "the wrong type: {invalid_type} "
                    "- should have been {valid_type}".format(
                        key=key,
                        invalid_type=type(value).__name__,
                        valid_type=self.options[key].__name__))
                continue

            options[key] = value

        return options

    def filter_members(self, members):
        # Can be overridden by inherited classes
        return members

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        attr_values = self.get_attr_values_from_data(instance.data)

        # Load plugin first
        cmds.loadPlugin("mayaUsdPlugin", quiet=True)

        # Define output file path
        staging_dir = self.staging_dir(instance)
        file_name = "{0}.usd".format(instance.name)
        file_path = os.path.join(staging_dir, file_name)
        file_path = file_path.replace('\\', '/')

        # Parse export options
        options = self.default_options
        options = self.parse_overrides(instance, options)
        self.log.debug("Export options: {0}".format(options))

        # Perform extraction
        self.log.debug("Performing extraction ...")

        members = instance.data("setMembers")
        self.log.debug('Collected objects: {}'.format(members))
        members = self.filter_members(members)
        if not members:
            self.log.error('No members!')
            return

        export_anim_data = instance.data.get("exportAnimationData", True)
        start = instance.data.get("frameStartHandle", 0)

        if export_anim_data:
            end = instance.data["frameEndHandle"]
            options["frameRange"] = (start, end)
            options["frameStride"] = instance.data.get("step", 1.0)

        if instance.data.get("exportRoots", True):
            # Do not include 'objectSets' as roots because the export command
            # will fail. We only include the transforms among the members.
            options["exportRoots"] = cmds.ls(members,
                                             type="transform",
                                             long=True)
        else:
            options["selection"] = True

        options["stripNamespaces"] = attr_values.get("stripNamespaces", True)
        options["exportComponentTags"] = attr_values.get("exportComponentTags",
                                                         False)

        # TODO: Remove hardcoded filterTypes
        # We always filter constraint types because they serve no valuable
        # data (it doesn't preserve the actual constraint) but it does
        # introduce the problem that Shapes do not merge into the Transform
        # on export anymore because they are usually parented under transforms
        # See: https://github.com/Autodesk/maya-usd/issues/2070
        options["filterTypes"] = ["constraint"]

        def parse_attr_str(attr_str):
            """Return list of strings from `a,b,c,,d` to `[a, b, c, d]`.

            Args:
                attr_str (str): Concatenated attributes by comma

            Returns:
                List[str]: list of attributes
            """
            result = list()
            for attr in attr_str.split(","):
                attr = attr.strip()
                if not attr:
                    continue
                result.append(attr)
            return result

        attrs = parse_attr_str(instance.data.get("attr", ""))
        attrs += instance.data.get("userDefinedAttributes", [])
        attrs += ["cbId"]
        attr_prefixes = parse_attr_str(instance.data.get("attrPrefix", ""))

        # Remove arguments for Maya USD versions not supporting them yet
        # Note: Maya 2022.3 ships with Maya USD 0.13.0.
        # TODO: Remove this backwards compatibility if Maya 2022 support is
        #   dropped
        maya_usd_version = parse_version(
            cmds.pluginInfo("mayaUsdPlugin", query=True, version=True)
        )
        for key, required_minimal_version in {
            "exportComponentTags": (0, 14, 0),
            "jobContext": (0, 15, 0)
        }.items():
            if key in options and maya_usd_version < required_minimal_version:
                self.log.warning(
                    "Ignoring export flag '%s' because Maya USD version "
                    "%s is lower than minimal supported version %s.",
                    key,
                    maya_usd_version,
                    required_minimal_version
                )
                del options[key]

        self.log.debug('Exporting USD: {} / {}'.format(file_path, members))
        with maintained_time():
            with maintained_selection():
                if not export_anim_data:
                    # Use start frame as current time
                    cmds.currentTime(start)

                with usd_export_attributes(instance[:],
                                           attrs=attrs,
                                           attr_prefixes=attr_prefixes):
                    cmds.select(members, replace=True, noExpand=True)
                    cmds.mayaUSDExport(file=file_path,
                                       **options)

        representation = {
            'name': "usd",
            'ext': "usd",
            'files': file_name,
            'stagingDir': staging_dir
        }
        instance.data.setdefault("representations", []).append(representation)

        self.log.debug(
            "Extracted instance {} to {}".format(instance.name, file_path)
        )

    @classmethod
    def get_attribute_defs(cls):
        return super(ExtractMayaUsd, cls).get_attribute_defs() + [
            BoolDef("stripNamespaces",
                    label="Strip Namespaces (USD)",
                    tooltip="Strip Namespaces in the USD Export",
                    default=True),
            BoolDef("exportComponentTags",
                    label="Export Component Tags",
                    tooltip="When enabled, export any geometry component tags "
                            "as UsdGeomSubset data.",
                    default=False)
        ]


class ExtractMayaUsdAnim(ExtractMayaUsd):
    """Extractor for Maya USD Animation Sparse Cache data.

    This will extract the sparse cache data from the scene and generate a
    USD file with all the animation data.

    Upon publish a .usd sparse cache will be written.
    """
    label = "Extract USD Animation"
    families = ["animation"]

    optional = True
    active = False

    # TODO: Support writing out point deformation only, avoid writing UV sets
    #       component tags and potentially remove `faceVertexCounts`,
    #       `faceVertexIndices` and `doubleSided` parameters as well.
    def filter_members(self, members):
        out_set = next((i for i in members if i.endswith("out_SET")), None)

        if out_set is None:
            self.log.warning("Expecting out_SET")
            return None

        members = cmds.ls(cmds.sets(out_set, query=True), long=True)
        return members


class ExtractMayaUsdModel(ExtractMayaUsd):
    """Extractor for Maya USD Asset data for model family

    Upon publish a .usd (or .usdz) asset file will typically be written.
    """

    label = "Extract USD"
    families = ["model"]

    # TODO: Expose in settings
    optional = True

    def process(self, instance):
        # TODO: Fix this without changing instance data
        instance.data["exportAnimationData"] = False
        super(ExtractMayaUsdModel, self).process(instance)


class ExtractMayaUsdPointcache(ExtractMayaUsd):
    """Extractor for Maya USD for 'pointcache' family"""

    label = "Extract USD"
    families = ["pointcache"]

    # TODO: Expose in settings
    optional = True
    active = False
