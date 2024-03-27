import dataclasses
import os
import logging

try:
    from pxr import Usd, UsdGeom, Sdf, Kind
except ImportError:
    # Allow to fall back on Multiverse 6.3.0+ pxr usd library
    from mvpxr import Usd, UsdGeom, Sdf, Kind

log = logging.getLogger(__name__)


@dataclasses.dataclass
class Layer:
    layer: Sdf.Layer
    path: str
    # Allow to anchor a layer to another so that when the layer would be
    # exported it'd write itself out relative to its anchor
    anchor: 'Layer' = None

    @property
    def identifier(self):
        return self.layer.identifier

    def get_full_path(self):
        """Return full path relative to the anchor layer"""
        if not os.path.isabs(self.path) and self.anchor:
            anchor_path = self.anchor.get_full_path()
            root = os.path.dirname(anchor_path)
            return os.path.normpath(os.path.join(root, self.path))
        else:
            return self.path

    def export(self, path=None, args=None):
        """Save the layer"""
        if path is None:
            path = self.get_full_path()

        if args is None:
            args = self.layer.GetFileFormatArguments()

        self.layer.Export(path, args=args)

    @classmethod
    def create_anonymous(cls, path, tag="LOP", anchor=None):
        sdf_layer = Sdf.Layer.CreateAnonymous(tag)
        return cls(layer=sdf_layer, path=path, anchor=anchor, tag=tag)


def setup_asset_layer(
        layer,
        asset_name,
        reference_layers=None,
        kind=Kind.Tokens.component,
        define_class=True,
        force_add_payload=False,
        set_payload_path=False
):
    """
    Adds an asset prim to the layer with the `reference_layers` added as
    references for e.g. geometry and shading.

    The referenced layers will be moved into a separate `./payload.usd` file
    that the asset file uses to allow deferred loading of the heavier
    geometrical data. An example would be:

    asset.usd      <-- out filepath
      payload.usd  <-- always automatically added in-between
        look.usd   <-- reference layer 0 from `reference_layers` argument
        model.usd  <-- reference layer 1 from `reference_layers` argument

    If `define_class` is enabled then a `/__class__/{asset_name}` class
    definition will be created that the root asset inherits from

    Examples:
        >>> create_asset("/path/to/asset.usd",
        >>>              asset_name="test",
        >>>              reference_layers=["./model.usd", "./look.usd"])

    Returns:
        List[Tuple[Sdf.Layer, str]]: List of created layers with their
            preferred output save paths.

    Args:
        layer (Sdf.Layer): Layer to set up the asset structure for.
        asset_name (str): The name for the Asset identifier and default prim.
        reference_layers (list): USD Files to reference in the asset.
            Note that the bottom layer (first file, like a model) would
            be last in the list. The strongest layer will be the first
            index.
        kind (pxr.Kind): A USD Kind for the root asset.
        define_class: Define a `/__class__/{asset_name}` class which the
            root asset prim will inherit from.
        force_add_payload (bool): Generate payload layer even if no
            reference paths are set - thus generating an enmpty layer.
        set_payload_path (bool): Whether to directly set the payload asset
            path to `./payload.usd` or not Defaults to True.

    """
    # Define root prim for the asset and make it the default for the stage.
    prim_name = asset_name

    if define_class:
        class_prim = Sdf.PrimSpec(
            layer.pseudoRoot,
            "__class__",
            Sdf.SpecifierClass,
        )
        Sdf.PrimSpec(
            class_prim,
            prim_name,
            Sdf.SpecifierClass,
        )

    asset_prim = Sdf.PrimSpec(
        layer.pseudoRoot,
        prim_name,
        Sdf.SpecifierDef,
        "Xform"
    )

    if define_class:
        asset_prim.inheritPathList.prependedItems[:] = [
            "/__class__/{}".format(prim_name)
        ]

    # Define Kind
    # Usually we will "loft up" the kind authored into the exported geometry
    # layer rather than re-stamping here; we'll leave that for a later
    # tutorial, and just be explicit here.
    asset_prim.kind = kind

    # Set asset info
    asset_prim.assetInfo["name"] = asset_name
    asset_prim.assetInfo["identifier"] = "%s/%s.usd" % (asset_name, asset_name)

    # asset.assetInfo["version"] = asset_version
    set_layer_defaults(layer, default_prim=asset_name)

    created_layers = []

    # Add references to the  asset prim
    if force_add_payload or reference_layers:
        # Create a relative payload file to filepath through which we sublayer
        # the heavier payloads
        # Prefix with `LOP` just so so that if Houdini ROP were to save
        # the nodes it's capable of exporting with explicit save path
        payload_layer = Sdf.Layer.CreateAnonymous("LOP",
                                                  args={"format": "usda"})
        set_layer_defaults(payload_layer, default_prim=asset_name)
        created_layers.append(Layer(layer=payload_layer,
                                    path="./payload.usd"))

        # Add payload
        if set_payload_path:
            payload_identifier = "./payload.usd"
        else:
            payload_identifier = payload_layer.identifier

        asset_prim.payloadList.prependedItems[:] = [
            Sdf.Payload(assetPath=payload_identifier)
        ]

        # Add sublayers to the payload layer
        # Note: Sublayering is tricky because it requires that the sublayers
        #   actually define the path at defaultPrim otherwise the payload
        #   reference will not find the defaultPrim and turn up empty.
        if reference_layers:
            for ref_layer in reference_layers:
                payload_layer.subLayerPaths.append(ref_layer)

    return created_layers


def create_asset(
        filepath,
        asset_name,
        reference_layers=None,
        kind=Kind.Tokens.component,
        define_class=True
):
    """Creates and saves a prepared asset stage layer.

    Creates an asset file that consists of a top level asset prim, asset info
     and references in the provided `reference_layers`.

    Returns:
        list: Created layers

    """
    # Also see create_asset.py in PixarAnimationStudios/USD endToEnd example

    sdf_layer = Sdf.Layer.CreateAnonymous()
    layer = Layer(layer=sdf_layer, path=filepath)

    created_layers = setup_asset_layer(
        layer=sdf_layer,
        asset_name=asset_name,
        reference_layers=reference_layers,
        kind=kind,
        define_class=define_class,
        set_payload_path=True
    )
    for created_layer in created_layers:
        created_layer.anchor = layer
        created_layer.export()

    # Make the layer ascii - good for readability, plus the file is small
    log.debug("Creating asset at %s", filepath)
    layer.export(args={"format": "usda"})

    return [layer] + created_layers


def create_shot(filepath, layers, create_layers=False):
    """Create a shot with separate layers for departments.

    Examples:
        >>> create_shot("/path/to/shot.usd",
        >>>             layers=["lighting.usd", "fx.usd", "animation.usd"])
        "/path/to/shot.usd"

    Args:
        filepath (str): Filepath where the asset.usd file will be saved.
        layers (list): When provided this will be added verbatim in the
            subLayerPaths layers. When the provided layer paths do not exist
            they are generated using Sdf.Layer.CreateNew
        create_layers (bool): Whether to create the stub layers on disk if
            they do not exist yet.

    Returns:
        str: The saved shot file path

    """
    # Also see create_shot.py in PixarAnimationStudios/USD endToEnd example
    root_layer = Sdf.Layer.CreateAnonymous()

    created_layers = [root_layer]
    for layer_path in layers:
        if create_layers and not os.path.exists(layer_path):
            # We use the Sdf API here to quickly create layers.  Also, we're
            # using it as a way to author the subLayerPaths as there is no
            # way to do that directly in the Usd API.
            layer_folder = os.path.dirname(layer_path)
            if not os.path.exists(layer_folder):
                os.makedirs(layer_folder)

            new_layer = Sdf.Layer.CreateNew(layer_path)
            created_layers.append(new_layer)

        root_layer.subLayerPaths.append(layer_path)

    set_layer_defaults(root_layer)
    log.debug("Creating shot at %s" % filepath)
    root_layer.Export(filepath, args={"format": "usda"})

    return created_layers


def add_ordered_sublayer(layer, contribution_path, layer_id, order=None,
                         add_sdf_arguments_metadata=True):
    """Add sublayer paths in the Sdf.Layer at given "orders"

    USD does not provide a way to set metadata per sublayer entry, but we can
    'sneak it in' by adding it as part of the file url after :SDF_FORMAT_ARGS:
    There they will then just be unused args that we can parse later again
    to access our data.

    A higher order will appear earlier in the subLayerPaths as a stronger
    opinion. An unordered layer (`order=None`) will be stronger than any
    ordered opinion and thus will be inserted at the start of the list.

    Args:
        layer (Sdf.Layer): Layer to add sublayers in.
        contribution_path (str): Path/URI to add.
        layer_id (str): Token that if found for an existing layer it will
            replace that layer.
        order (Any[int, None]): Order to place the contribution in
            the sublayers. When `None` no ordering is considered nor will
            ordering metadata be written if `add_sdf_arguments_metadata` is
            False.
        add_sdf_arguments_metadata (bool): Add metadata into the filepath
            to store the `layer_id` and `order` so ordering can be maintained
            in the future as intended.

    Returns:
        str: The resulting contribution path (which maybe include the
            sdf format args metadata if enabled)

    """

    # Add the order with the contribution path so that for future
    # contributions we can again use it to magically fit into the
    # ordering. We put this in the path because sublayer paths do
    # not allow customData to be stored.
    def _format_path(path, layer_id, order):
        # TODO: Avoid this hack to store 'order' and 'layer' metadata
        #   for sublayers; in USD sublayers can't hold customdata
        if not add_sdf_arguments_metadata:
            return path
        data = {"layer_id": str(layer_id)}
        if order is not None:
            data["order"] = str(order)
        return Sdf.Layer.CreateIdentifier(path, data)

    # If the layer was already in the layers, then replace it
    for index, existing_path in enumerate(layer.subLayerPaths):
        args = get_sdf_format_args(existing_path)
        existing_layer = args.get("layer_id")
        if existing_layer == layer_id:
            # Put it in the same position where it was before when swapping
            # it with the original, also take over its order metadata
            order = args.get("order")
            if order is not None:
                order = int(order)
            else:
                order = None
            contribution_path = _format_path(contribution_path,
                                             order=order,
                                             layer_id=layer_id)
            log.debug(
                f"Replacing existing layer: {layer.subLayerPaths[index]} "
                f"-> {contribution_path}"
            )
            layer.subLayerPaths[index] = contribution_path
            return contribution_path

    contribution_path = _format_path(contribution_path,
                                     order=order,
                                     layer_id=layer_id)

    # If an order is defined and other layers are ordered than place it before
    # the first order where existing order is lower
    if order is not None:
        for index, existing_path in enumerate(layer.subLayerPaths):
            args = get_sdf_format_args(existing_path)
            existing_order = args.get("order")
            if existing_order is not None and int(existing_order) < order:
                log.debug(
                    f"Inserting new layer at {index}: {contribution_path}"
                )
                layer.subLayerPaths.insert(index, contribution_path)
                return
        # Weakest ordered opinion
        layer.subLayerPaths.append(contribution_path)
        return contribution_path

    # If no paths found with an order to put it next to
    # then put the sublayer at the end
    log.debug(f"Appending new layer: {contribution_path}")
    layer.subLayerPaths.insert(0, contribution_path)
    return contribution_path


def add_variant_references_to_layer(
    variants,
    variantset,
    default_variant=None,
    variant_prim="/root",
    reference_prim=None,
    set_default_variant=True,
    as_payload=False,
    skip_variant_on_single_file=False,
    layer=None
):
    """Add or set a prim's variants to reference specified paths in the layer.

    Note:
        This does not clear any of the other opinions than replacing
        `prim.referenceList.prependedItems` with the new reference.
        If `as_payload=True` then this only does it for payloads and leaves
        references as they were in-tact.

    Note:
        If `skip_variant_on_single_file=True` it does *not* check if any
        other variants do exist; it only checks whether you are currently
        adding more than one since it'd be hard to find out whether previously
        this was also skipped and should now if you're adding a new one
        suddenly also be its original 'variant'. As such it's recommended to
        keep this disabled unless you know you're not updating the file later
        into the same variant set.

    Examples:
    >>> layer = add_variant_references_to_layer("model.usd",
    >>>     variants=[
    >>>         ("main", "main.usd"),
    >>>         ("damaged", "damaged.usd"),
    >>>         ("twisted", "twisted.usd")
    >>>     ],
    >>>     variantset="model")
    >>> layer.Export("model.usd", args={"format": "usda"})

    Arguments:
        variants (List[List[str, str]): List of two-tuples of variant name to
            the filepath that should be referenced in for that variant.
        variantset (str): Name of the variant set
        default_variant (str): Default variant to set. If not provided
            the first variant will be used.
        variant_prim (str): Variant prim?
        reference_prim (str): Path to the reference prim where to add the
            references and variant sets.
        set_default_variant (bool): Whether to set the default variant.
            When False no default variant will be set, even if a value
            was provided to `default_variant`
        as_payload (bool): When enabled, instead of referencing use payloads
        skip_variant_on_single_file (bool): If this is enabled and only
            a single variant is provided then do not create the variant set
            but just reference that single file.
        layer (Sdf.Layer): When provided operate on this layer, otherwise
            create an anonymous layer in memory.

    Returns:
        Usd.Stage: The saved usd stage

    """
    if layer is None:
        layer = Sdf.Layer.CreateAnonymous()
        set_layer_defaults(layer, default_prim=variant_prim.strip("/"))

    prim_path_to_get_variants = Sdf.Path(variant_prim)
    root_prim = get_or_define_prim_spec(layer, variant_prim, "Xform")

    # TODO: Define why there's a need for separate variant_prim and
    #   reference_prim attribute. When should they differ? Does it even work?
    if not reference_prim:
        reference_prim = root_prim
    else:
        reference_prim = get_or_define_prim_spec(layer, reference_prim,
                                                 "Xform")

    assert variants, "Must have variants, got: %s" % variants

    if skip_variant_on_single_file and len(variants) == 1:
        # Reference directly, no variants
        variant_path = variants[0][1]
        if as_payload:
            # Payload
            reference_prim.payloadList.prependedItems.append(
                Sdf.Payload(variant_path)
            )
        else:
            # Reference
            reference_prim.referenceList.prependedItems.append(
                Sdf.Reference(variant_path)
            )

        log.debug("Creating without variants due to single file only.")
        log.debug("Path: %s", variant_path)

    else:
        # Variants
        for variant, variant_filepath in variants:
            if default_variant is None:
                default_variant = variant

            set_variant_reference(layer,
                                  prim_path=prim_path_to_get_variants,
                                  variant_selections=[[variantset, variant]],
                                  path=variant_filepath,
                                  as_payload=as_payload)

        if set_default_variant and default_variant is not None:
            # Set default variant selection
            root_prim.variantSelections[variantset] = default_variant

    return layer


def set_layer_defaults(layer,
                       up_axis=UsdGeom.Tokens.y,
                       meters_per_unit=1.0,
                       default_prim=None):
    """Set some default metadata for the SdfLayer.

    Arguments:
        layer (Sdf.Layer): The layer to set default for via Sdf API.
        up_axis (UsdGeom.Token); Which axis is the up-axis
        meters_per_unit (float): Meters per unit
        default_prim (Optional[str]: Default prim name

    """
    # Set default prim
    if default_prim is not None:
        layer.defaultPrim = default_prim

    # Let viewing applications know how to orient a free camera properly
    # Similar to: UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    layer.pseudoRoot.SetInfo(UsdGeom.Tokens.upAxis, up_axis)

    # Set meters per unit
    layer.pseudoRoot.SetInfo(UsdGeom.Tokens.metersPerUnit,
                             float(meters_per_unit))


def get_or_define_prim_spec(layer, prim_path, type_name):
    """Get or create a PrimSpec in the layer.

    Note:
        This creates a Sdf.PrimSpec with Sdf.SpecifierDef but if the PrimSpec
        already exists this will not force it to be a Sdf.SpecifierDef and
        it may remain what it was, e.g. Sdf.SpecifierOver

    Args:
        layer (Sdf.Layer): The layer to create it in.
        prim_path (Any[str, Sdf.Path]): Prim path to create.
        type_name (str): Type name for the PrimSpec.
            This will only be set if the prim does not exist in the layer
            yet. It does not update type for an existing prim.

    Returns:
        Sdf.PrimSpec: The PrimSpec in the layer for the given prim path.

    """
    prim_spec = layer.GetPrimAtPath(prim_path)
    if prim_spec:
        return prim_spec

    prim_spec = Sdf.CreatePrimInLayer(layer, prim_path)
    prim_spec.specifier = Sdf.SpecifierDef
    prim_spec.typeName = type_name
    return prim_spec


def variant_nested_prim_path(prim_path, variant_selections):
    """Return the Sdf.Path for a nested variant selection at prim path.

    Examples:
    >>> prim_path = Sdf.Path("/asset")
    >>> variant_spec = variant_nested_prim_path(
    >>>     prim_path,
    >>>     variant_selections=[["model", "main"], ["look", "main"]]
    >>> )
    >>> variant_spec.path

    Args:
        prim_path (Sdf.PrimPath): The prim path to create the spec in
        variant_selections (List[List[str, str]]): A list of variant set names
            and variant names to get the prim spec in.

    Returns:
        Sdf.Path: The variant prim path

    """
    variant_prim_path = Sdf.Path(prim_path)
    for variant_set_name, variant_name in variant_selections:
        variant_prim_path = variant_prim_path.AppendVariantSelection(
            variant_set_name, variant_name)
    return variant_prim_path


def add_ordered_reference(
        layer,
        prim_path,
        reference,
        order
):
    """Add reference alongside other ordered references.

    Args:
        layer (Sdf.Layer): Layer to operate in.
        prim_path (Sdf.Path): Prim path to reference into.
            This may include variant selections to reference into a prim
            inside the variant selection.
        reference (Sdf.Reference): Reference to add.
        order  (int): Order.

    Returns:
        Sdf.PrimSpec: The prim spec for the prim path.

    """
    assert isinstance(order, int), "order must be integer"

    # Sdf.Reference is immutable, see: `pxr/usd/sdf/wrapReference.cpp`
    # A Sdf.Reference can't be edited in Python so we create a new entry
    # matching the original with the extra data entry added.
    custom_data = reference.customData
    custom_data["ayon_order"] = order
    reference = Sdf.Reference(
        assetPath=reference.assetPath,
        primPath=reference.primPath,
        layerOffset=reference.layerOffset,
        customData=custom_data
    )

    # TODO: inherit type from outside of variants if it has it
    prim_spec = get_or_define_prim_spec(layer, prim_path, "Xform")

    # Insert new entry at correct order
    entries = list(prim_spec.referenceList.prependedItems)

    if not entries:
        prim_spec.referenceList.prependedItems.append(reference)
        return prim_spec

    for index, existing_ref in enumerate(entries):
        existing_order = existing_ref.customData.get("order")
        if existing_order is not None and existing_order < order:
            log.debug(
                f"Inserting new reference at {index}: {reference}"
            )
            entries.insert(index, reference)
            break
    else:
        prim_spec.referenceList.prependedItems.append(reference)
        return prim_spec

    prim_spec.referenceList.prependedItems[:] = entries
    return prim_spec


def set_variant_reference(sdf_layer, prim_path, variant_selections, path,
                          as_payload=False,
                          append=True):
    """Get or define variant selection at prim path and add a reference

    If the Variant Prim already exists the prepended references are replaced
    with a reference to `path`, it is overridden.

    Args:
        sdf_layer (Sdf.Layer): Layer to operate in.
        prim_path (Any[str, Sdf.Path]): Prim path to add variant to.
        variant_selections (List[List[str, str]]): A list of variant set names
            and variant names to get the prim spec in.
        path (str): Path to reference or payload
        as_payload (bool): When enabled it will generate a payload instead of
            a reference. Defaults to False.
        append (bool): When enabled it will append the reference of payload
            to prepended items, otherwise it will replace it.

    Returns:
        Sdf.PrimSpec: The prim spec for the prim path at the given
            variant selection.

    """
    prim_path = Sdf.Path(prim_path)
    # TODO: inherit type from outside of variants if it has it
    get_or_define_prim_spec(sdf_layer, prim_path, "Xform")
    variant_prim_path = variant_nested_prim_path(prim_path, variant_selections)
    variant_prim = get_or_define_prim_spec(sdf_layer,
                                           variant_prim_path,
                                           "Xform")
    # Replace the prepended references or payloads
    if as_payload:
        # Payload
        if append:
            variant_prim.payloadList.prependedItems.append(
                Sdf.Payload(assetPath=path)
            )
        else:
            variant_prim.payloadList.prependedItems[:] = [
                Sdf.Payload(assetPath=path)
            ]
    else:
        # Reference
        if append:
            variant_prim.referenceList.prependedItems.append(
                Sdf.Reference(assetPath=path)
            )
        else:
            variant_prim.referenceList.prependedItems[:] = [
                Sdf.Reference(assetPath=path)
            ]

    return variant_prim


def get_sdf_format_args(path):
    """Return SDF_FORMAT_ARGS parsed to `dict`"""
    _raw_path, data = Sdf.Layer.SplitIdentifier(path)
    return data
