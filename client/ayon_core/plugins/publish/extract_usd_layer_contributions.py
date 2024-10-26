from operator import attrgetter
import dataclasses
import os
from typing import Dict

import pyblish.api
try:
    from pxr import Sdf
except ImportError:
    Sdf = None

from ayon_core.lib import (
    TextDef,
    BoolDef,
    UISeparatorDef,
    UILabelDef,
    EnumDef,
    filter_profiles
)
try:
    from ayon_core.pipeline.usdlib import (
        get_or_define_prim_spec,
        add_ordered_reference,
        variant_nested_prim_path,
        setup_asset_layer,
        add_ordered_sublayer,
        set_layer_defaults
    )
except ImportError:
    pass
from ayon_core.pipeline.entity_uri import (
    construct_ayon_entity_uri,
    parse_ayon_entity_uri
)
from ayon_core.pipeline.load.utils import get_representation_path_by_names
from ayon_core.pipeline.publish.lib import get_instance_expected_output_path
from ayon_core.pipeline import publish, KnownPublishError


# This global toggle is here mostly for debugging purposes and should usually
# be True so that new publishes merge and extend on previous contributions.
# With this enabled a new variant model layer publish would e.g. merge with
# the model layer's other variants nicely, so you can build up an asset by
# individual publishes instead of requiring to republish each contribution
# all the time at the same time
BUILD_INTO_LAST_VERSIONS = True


@dataclasses.dataclass
class _BaseContribution:
    # What are we contributing?
    instance: pyblish.api.Instance  # instance that contributes it

    # Where are we contributing to?
    layer_id: str  # usually the department or task name
    target_product: str  # target product the layer should merge to

    order: int


class SublayerContribution(_BaseContribution):
    """Sublayer contribution"""


@dataclasses.dataclass
class VariantContribution(_BaseContribution):
    """Reference contribution within a Variant Set"""

    # Variant
    variant_set_name: str
    variant_name: str
    variant_is_default: bool  # Whether to author variant selection opinion


def get_representation_path_in_publish_context(
    context: pyblish.api.Context,
    project_name,
    folder_path,
    product_name,
    version_name,
    representation_name,
):
    """Return resolved path for product if present in publishing context.

    Allow resolving 'latest' paths from a publishing context's instances
    as if they will exist after publishing without them being integrated yet.

    Use first instance that has same folder path and product name,
    and contains representation with passed name.

    Args:
        context (pyblish.api.Context): Publishing context.
        project_name (str): Project name.
        folder_path (str): Folder path.
        product_name (str): Product name.
        version_name (str): Version name.
        representation_name (str): Representation name.

    Returns:
        Union[str, None]: Returns the path if it could be resolved

    """
    # The AYON publishing logic is set up in such a way that you can not
    # publish to another project. As such, we know if the project name we're
    # looking for doesn't match the publishing context it'll not be in there.
    if context.data["projectName"] != project_name:
        return

    if version_name == "hero":
        raise NotImplementedError(
            "Hero version resolving not implemented from context"
        )

    # Search first in publish context to allow resolving latest versions
    # from e.g. the current publish session if the context is provided
    specific_version = isinstance(version_name, int)
    for instance in context:
        if instance.data.get("folderPath") != folder_path:
            continue

        if instance.data.get("productName") != product_name:
            continue

        # Only consider if the instance has a representation by
        # that name
        representations = instance.data.get("representations", [])
        if not any(representation.get("name") == representation_name
                   for representation in representations):
            continue

        return get_instance_expected_output_path(
            instance,
            representation_name=representation_name,
            ext=None,
            version=version_name if specific_version else None
        )


def get_instance_uri_path(
        instance,
        resolve=True
):
    """Return path for instance's usd representation"""
    context = instance.context
    folder_path = instance.data["folderPath"]
    product_name = instance.data["productName"]
    project_name = context.data["projectName"]
    version_name = instance.data["version"]

    # Get the layer's published path
    path = construct_ayon_entity_uri(
        project_name=project_name,
        folder_path=folder_path,
        product=product_name,
        version=version_name,
        representation_name="usd"
    )

    # Resolve contribution path
    # TODO: Remove this when Asset Resolver is used
    if resolve:
        query = parse_ayon_entity_uri(path)
        names = {
            "project_name": query["project"],
            "folder_path": query["folderPath"],
            "product_name": query["product"],
            "version_name": query["version"],
            "representation_name": query["representation"],
        }

        # We want to resolve the paths live from the publishing context
        path = get_representation_path_in_publish_context(context, **names)
        if path:
            return path

        # If for whatever reason we were unable to retrieve from the context
        # then get the path from an existing database entry
        path = get_representation_path_by_names(**query)

        # Ensure `None` for now is also a string
        path = str(path)

    return path


def get_last_publish(instance, representation="usd"):
    """Wrapper to quickly get last representation publish path"""
    return get_representation_path_by_names(
        project_name=instance.context.data["projectName"],
        folder_path=instance.data["folderPath"],
        product_name=instance.data["productName"],
        version_name="latest",
        representation_name=representation
    )


def add_representation(instance, name,
                       files, staging_dir, ext=None,
                       output_name=None):
    """Add a representation to publish and integrate.

    A representation must exist of either a single file or a
    single file sequence. It can *not* contain multiple files.

    For the integration to succeed the instance must provide the context
    for asset, frame range, etc. even though the representation can
    override some parts of it.

    Arguments:
        instance (pyblish.api.Instance): Publish instance
        name (str): The representation name
        files (str | List[str]): List of files or single file of the
            representation. This should be the filename only.
        staging_dir (str): The directory containing the files.
        ext (Optional[str]): Explicit extension for the output
        output_name (Optional[str]): Output name suffix for the
            destination file to ensure the file is unique if
            multiple representations share the same extension.

    Returns:
        dict: Representation data for integration.

    """
    if ext is None:
        # TODO: Use filename
        ext = name

    representation = {
        "name": name,
        "ext": ext,
        "stagingDir": staging_dir,
        "files": files
    }
    if output_name:
        representation["outputName"] = output_name

    instance.data.setdefault("representations", []).append(representation)
    return representation


class CollectUSDLayerContributions(pyblish.api.InstancePlugin,
                                   publish.AYONPyblishPluginMixin):
    """Collect the USD Layer Contributions and create dependent instances.

    Our contributions go to the layer

        Instance representation -> Department Layer -> Asset

    So that for example:
        modelMain --> variant 'main' in model.usd -> asset.usd
        modelDamaged --> variant 'damaged' in model.usd -> asset.usd

    """

    order = pyblish.api.CollectorOrder + 0.35
    label = "Collect USD Layer Contributions (Asset/Shot)"
    families = ["usd"]
    enabled = True

    # A contribution defines a contribution into a (department) layer which
    # will get layered into the target product, usually the asset or shot.
    # We need to at least know what it targets (e.g. where does it go into) and
    # in what order (which contribution is stronger?)
    # Preferably the bootstrapped data (e.g. the Shot) preserves metadata about
    # the contributions so that we can design a system where custom
    # contributions outside the predefined orders are possible to be
    # managed. So that if a particular asset requires an extra contribution
    # level, you can add itdirectly from the publisher at that particular
    # order. Future publishes will then see the existing contribution and will
    # persist adding it to future bootstraps at that order
    contribution_layers: Dict[str, int] = {
        # asset layers
        "model": 100,
        "assembly": 150,
        "groom": 175,
        "look": 200,
        "rig": 300,
        # shot layers
        "layout": 200,
        "animation": 300,
        "simulation": 400,
        "fx": 500,
        "lighting": 600,
    }

    @classmethod
    def apply_settings(cls, project_settings):
        # Override contribution_layers logic to turn data into Dict[str, int]
        plugin_settings = project_settings["core"]["publish"].get(
            "CollectUSDLayerContributions", {}
        )

        cls.enabled = plugin_settings.get("enabled", cls.enabled)

        # Define contribution layers via settings
        contribution_layers = {}
        for entry in plugin_settings.get("contribution_layers", []):
            contribution_layers[entry["name"]] = int(entry["order"])
        if contribution_layers:
            cls.contribution_layers = contribution_layers

    def process(self, instance):

        attr_values = self.get_attr_values_from_data(instance.data)
        if not attr_values.get("contribution_enabled"):
            return

        instance.data["productGroup"] = (
            instance.data.get("productGroup") or "USD Layer"
        )

        # Allow formatting in variant set name and variant name
        data = instance.data.copy()
        data["layer"] = attr_values["contribution_layer"]
        for key in [
            "contribution_variant_set_name",
            "contribution_variant"
        ]:
            attr_values[key] = attr_values[key].format(**data)

        # Define contribution
        order = self.contribution_layers.get(
            attr_values["contribution_layer"], 0
        )

        if attr_values["contribution_apply_as_variant"]:
            contribution = VariantContribution(
                instance=instance,
                layer_id=attr_values["contribution_layer"],
                target_product=attr_values["contribution_target_product"],
                variant_set_name=attr_values["contribution_variant_set_name"],
                variant_name=attr_values["contribution_variant"],
                variant_is_default=attr_values["contribution_variant_is_default"],  # noqa: E501
                order=order
            )
        else:
            contribution = SublayerContribution(
                instance=instance,
                layer_id=attr_values["contribution_layer"],
                target_product=attr_values["contribution_target_product"],
                order=order
            )

        asset_product = contribution.target_product
        layer_product = "{}_{}".format(asset_product, contribution.layer_id)

        # Layer contribution instance
        layer_instance = self.get_or_create_instance(
            product_name=layer_product,
            variant=contribution.layer_id,
            source_instance=instance,
            families=["usd", "usdLayer"],
        )
        layer_instance.data.setdefault("usd_contributions", []).append(
            contribution
        )
        layer_instance.data["usd_layer_id"] = contribution.layer_id
        layer_instance.data["usd_layer_order"] = contribution.order

        layer_instance.data["productGroup"] = (
            instance.data.get("productGroup") or "USD Layer"
        )

        # Asset/Shot contribution instance
        target_instance = self.get_or_create_instance(
            product_name=asset_product,
            variant=asset_product,
            source_instance=layer_instance,
            families=["usd", "usdAsset"],
        )
        target_instance.data["contribution_target_product_init"] = attr_values[
            "contribution_target_product_init"
        ]

        self.log.info(
            f"Contributing {instance.data['productName']} to "
            f"{layer_product} -> {asset_product}"
        )

    def find_instance(self, context, data, ignore_instance):
        """Return instance in context that has matching `instance.data`.

        If no matching instance is found, then `None` is returned.
        """
        for instance in context:
            if instance is ignore_instance:
                continue

            if all(instance.data.get(key) == value
                   for key, value in data.items()):
                return instance

    def get_or_create_instance(self,
                               product_name,
                               variant,
                               source_instance,
                               families):
        """Get or create the instance matching the product/variant.

        The source instance will be used to do additional matching, like
        ensuring it's a product for the same asset and task. If the instance
        already exists in the `context` then the existing one is returned.

        For each source instance this is called the sources will be appended
        to a `instance.data["source_instances"]` list on the returned instance.

        Arguments:
            product_name (str): product name
            variant (str): Variant name
            source_instance (pyblish.api.Instance): Source instance to
                be related to for asset, task.
            families (list): The families required to be set on the instance.

        Returns:
            pyblish.api.Instance: The resulting instance.

        """

        # Potentially the instance already exists due to multiple instances
        # contributing to the same layer or asset - so we first check for
        # existence
        context = source_instance.context

        # Required matching vars
        data = {
            "folderPath": source_instance.data["folderPath"],
            "task": source_instance.data.get("task"),
            "productName": product_name,
            "variant": variant,
            "families": families
        }
        existing_instance = self.find_instance(context, data,
                                               ignore_instance=source_instance)
        if existing_instance:
            existing_instance.append(source_instance.id)
            existing_instance.data["source_instances"].append(source_instance)
            return existing_instance

        # Otherwise create the instance
        new_instance = context.create_instance(name=product_name)
        new_instance.data.update(data)

        new_instance.data["label"] = (
            "{0} ({1})".format(product_name, new_instance.data["folderPath"])
        )
        new_instance.data["family"] = "usd"
        new_instance.data["productType"] = "usd"
        new_instance.data["icon"] = "link"
        new_instance.data["comment"] = "Automated bootstrap USD file."
        new_instance.append(source_instance.id)
        new_instance.data["source_instances"] = [source_instance]

        # The contribution target publishes should never match versioning of
        # the workfile but should just always increment from their last version
        # so that there will never be conflicts between contributions from
        # different departments and scenes.
        new_instance.data["followWorkfileVersion"] = False

        return new_instance

    @classmethod
    def get_attr_defs_for_instance(cls, create_context, instance):
        # Filtering of instance, if needed, can be customized
        if not cls.instance_matches_plugin_families(instance):
            return []

        # Set default target layer based on product type
        # TODO: Define profiles in settings
        profiles = [
            {
                "productType": "model",
                "contribution_layer": "model",
                "contribution_apply_as_variant": True,
                "contribution_target_product": "usdAsset"
            },
            {
                "productType": "look",
                "contribution_layer": "look",
                "contribution_apply_as_variant": True,
                "contribution_target_product": "usdAsset"
            },
            {
                "productType": "groom",
                "contribution_layer": "groom",
                "contribution_apply_as_variant": True,
                "contribution_target_product": "usdAsset"
            },
            {
                "productType": "rig",
                "contribution_layer": "rig",
                "contribution_apply_as_variant": True,
                "contribution_target_product": "usdShot"
            },
            {
                "productType": "usd",
                "contribution_layer": "assembly",
                "contribution_apply_as_variant": False,
                "contribution_target_product": "usdShot"
            },
        ]
        profile = filter_profiles(profiles, {
            "productType": instance.data["productType"]
        })
        if not profile:
            profile = {}

        # Define defaults
        default_contribution_layer = profile.get(
            "contribution_layer", None)
        default_apply_as_variant = profile.get(
            "contribution_apply_as_variant", False)
        default_target_product = profile.get(
            "contribution_target_product", "usdAsset")
        default_init_as = (
            "asset"
            if profile.get("contribution_target_product") == "usdAsset"
            else "shot")
        init_as_visible = False

        # Attributes logic
        publish_attributes = instance["publish_attributes"].get(
            cls.__name__, {})

        visible = publish_attributes.get("contribution_enabled", True)
        variant_visible = visible and publish_attributes.get(
            "contribution_apply_as_variant", True)

        return [
            UISeparatorDef("usd_container_settings1"),
            UILabelDef(label="<b>USD Contribution</b>"),
            BoolDef("contribution_enabled",
                    label="Enable",
                    tooltip=(
                        "When enabled this publish instance will be added "
                        "into a department layer into a target product, "
                        "usually an asset or shot.\n"
                        "When disabled this publish instance will not be "
                        "added into another USD file and remain as is.\n"
                        "In both cases the USD data itself is free to have "
                        "references and sublayers of its own."
                    ),
                    default=True),
            TextDef("contribution_target_product",
                    label="Target product",
                    tooltip=(
                        "The target product the contribution should be added "
                        "to. Usually this is the asset or shot product.\nThe "
                        "department layer will be added to this product, and "
                        "the contribution itself will be added to the "
                        "department layer."
                    ),
                    default=default_target_product,
                    visible=visible),
            EnumDef("contribution_target_product_init",
                    label="Initialize as",
                    tooltip=(
                        "The target product's USD file will be initialized "
                        "based on this type if there's no existing USD of "
                        "that product yet.\nIf there's already an existing "
                        "product with the name of the 'target product' this "
                        "setting will do nothing."
                    ),
                    items=["asset", "shot"],
                    default=default_init_as,
                    visible=visible and init_as_visible),

            # Asset layer, e.g. model.usd, look.usd, rig.usd
            EnumDef("contribution_layer",
                    label="Add to department layer",
                    tooltip=(
                        "The layer the contribution should be made to in the "
                        "target product.\nThe layers have their own "
                        "predefined ordering.\nA higher order (further down "
                        "the list) will contribute as a stronger opinion."
                    ),
                    items=list(cls.contribution_layers.keys()),
                    default=default_contribution_layer,
                    visible=visible),
            BoolDef("contribution_apply_as_variant",
                    label="Add as variant",
                    tooltip=(
                        "When enabled the contribution to the department "
                        "layer will be added as a variant where the variant "
                        "on the default root prim will be added as a "
                        "reference.\nWhen disabled the contribution will be "
                        "appended to as a sublayer to the department layer "
                        "instead."
                    ),
                    default=default_apply_as_variant,
                    visible=visible),
            TextDef("contribution_variant_set_name",
                    label="Variant Set Name",
                    default="{layer}",
                    visible=variant_visible),
            TextDef("contribution_variant",
                    label="Variant Name",
                    default="{variant}",
                    visible=variant_visible),
            BoolDef("contribution_variant_is_default",
                    label="Set as default variant selection",
                    tooltip=(
                        "Whether to set this instance's variant name as the "
                        "default selected variant name for the variant set.\n"
                        "It is always expected to be enabled for only one "
                        "variant name in the variant set.\n"
                        "The behavior is unpredictable if multiple instances "
                        "for the same variant set have this enabled."
                    ),
                    default=False,
                    visible=variant_visible),
            UISeparatorDef("usd_container_settings3"),
        ]

    @classmethod
    def register_create_context_callbacks(cls, create_context):
        create_context.add_value_changed_callback(cls.on_values_changed)

    @classmethod
    def on_values_changed(cls, event):
        """Update instance attribute definitions on attribute changes."""

        # Update attributes if any of the following plug-in attributes
        # change:
        keys = ["contribution_enabled", "contribution_apply_as_variant"]

        for instance_change in event["changes"]:
            instance = instance_change["instance"]
            if not cls.instance_matches_plugin_families(instance):
                continue
            value_changes = instance_change["changes"]
            plugin_attribute_changes = (
                value_changes.get("publish_attributes", {})
                .get(cls.__name__, {}))

            if not any(key in plugin_attribute_changes for key in keys):
                continue

            # Update the attribute definitions
            new_attrs = cls.get_attr_defs_for_instance(
                event["create_context"], instance
            )
            instance.set_publish_plugin_attr_defs(cls.__name__, new_attrs)


class ValidateUSDDependencies(pyblish.api.InstancePlugin):
    families = ["usdLayer"]

    order = pyblish.api.ValidatorOrder

    def process(self, instance):
        if Sdf is None:
            raise KnownPublishError("USD library 'Sdf' is not available.")


class ExtractUSDLayerContribution(publish.Extractor):

    families = ["usdLayer"]
    label = "Extract USD Layer Contributions (Asset/Shot)"
    order = pyblish.api.ExtractorOrder + 0.45

    use_ayon_entity_uri = False

    def process(self, instance):

        folder_path = instance.data["folderPath"]
        product_name = instance.data["productName"]
        self.log.debug(f"Building layer: {folder_path} > {product_name}")

        path = get_last_publish(instance)
        if path and BUILD_INTO_LAST_VERSIONS:
            sdf_layer = Sdf.Layer.OpenAsAnonymous(path)
            default_prim = sdf_layer.defaultPrim
        else:
            default_prim = folder_path.rsplit("/", 1)[-1]  # use folder name
            sdf_layer = Sdf.Layer.CreateAnonymous()
            set_layer_defaults(sdf_layer, default_prim=default_prim)

        contributions = instance.data.get("usd_contributions", [])
        for contribution in sorted(contributions, key=attrgetter("order")):
            path = get_instance_uri_path(contribution.instance,
                                         resolve=not self.use_ayon_entity_uri)
            if isinstance(contribution, VariantContribution):
                # Add contribution as a reference inside a variant
                self.log.debug(f"Adding variant: {contribution}")

                # Make sure at least the prim exists outside the variant
                # selection, so it can house the variant selection and the
                # variants themselves
                prim_path = Sdf.Path(f"/{default_prim}")
                prim_spec = get_or_define_prim_spec(sdf_layer,
                                                    prim_path,
                                                    "Xform")

                variant_prim_path = variant_nested_prim_path(
                    prim_path=prim_path,
                    variant_selections=[
                        (contribution.variant_set_name,
                         contribution.variant_name)
                    ]
                )

                # Remove any existing matching entry of same product
                variant_prim_spec = sdf_layer.GetPrimAtPath(variant_prim_path)
                if variant_prim_spec:
                    self.remove_previous_reference_contribution(
                        prim_spec=variant_prim_spec,
                        instance=contribution.instance
                    )

                # Add the contribution at the indicated order
                self.add_reference_contribution(sdf_layer,
                                                variant_prim_path,
                                                path,
                                                contribution)

                # Set default variant selection
                variant_set_name = contribution.variant_set_name
                variant_name = contribution.variant_name
                if contribution.variant_is_default or \
                        variant_set_name not in prim_spec.variantSelections:
                    prim_spec.variantSelections[variant_set_name] = variant_name  # noqa: E501

            elif isinstance(contribution, SublayerContribution):
                # Sublayer source file
                self.log.debug(f"Adding sublayer: {contribution}")

                # This replaces existing versions of itself so that
                # republishing does not continuously add more versions of the
                # same product
                product_name = contribution.instance.data["productName"]
                add_ordered_sublayer(
                    layer=sdf_layer,
                    contribution_path=path,
                    layer_id=product_name,
                    order=None,  # unordered
                    add_sdf_arguments_metadata=True
                )
            else:
                raise TypeError(f"Unsupported contribution: {contribution}")

        # Save the file
        staging_dir = self.staging_dir(instance)
        filename = f"{instance.name}.usd"
        filepath = os.path.join(staging_dir, filename)
        sdf_layer.Export(filepath, args={"format": "usda"})

        add_representation(
            instance,
            name="usd",
            files=filename,
            staging_dir=staging_dir
        )

    def remove_previous_reference_contribution(self,
                                               prim_spec: "Sdf.PrimSpec",
                                               instance: pyblish.api.Instance):
        # Remove existing contributions of the same product - ignoring
        # the picked version and representation. We assume there's only ever
        # one version of a product you want to have referenced into a Prim.
        remove_indices = set()
        for index, ref in enumerate(prim_spec.referenceList.prependedItems):
            ref: "Sdf.Reference"

            uri = ref.customData.get("ayon_uri")
            if uri and self.instance_match_ayon_uri(instance, uri):
                self.log.debug("Removing existing reference: %s", ref)
                remove_indices.add(index)

        if remove_indices:
            prim_spec.referenceList.prependedItems[:] = [
                ref for index, ref
                in enumerate(prim_spec.referenceList.prependedItems)
                if index not in remove_indices
            ]

    def add_reference_contribution(self,
                                   layer: "Sdf.Layer",
                                   prim_path: "Sdf.Path",
                                   filepath: str,
                                   contribution: VariantContribution):
        instance = contribution.instance
        uri = construct_ayon_entity_uri(
            project_name=instance.data["projectEntity"]["name"],
            folder_path=instance.data["folderPath"],
            product=instance.data["productName"],
            version=instance.data["version"],
            representation_name="usd"
        )
        reference = Sdf.Reference(assetPath=filepath,
                                  customData={"ayon_uri": uri})
        add_ordered_reference(
            layer=layer,
            prim_path=prim_path,
            reference=reference,
            order=contribution.order
        )

    def instance_match_ayon_uri(self, instance, ayon_uri):

        uri_data = parse_ayon_entity_uri(ayon_uri)
        if not uri_data:
            return False

        # Check if project, asset and product match
        if instance.data["projectEntity"]["name"] != uri_data.get("project"):
            return False

        if instance.data["folderPath"] != uri_data.get("folderPath"):
            return False

        if instance.data["productName"] != uri_data.get("product"):
            return False

        return True


class ExtractUSDAssetContribution(publish.Extractor):

    families = ["usdAsset"]
    label = "Extract USD Asset/Shot Contributions"
    order = ExtractUSDLayerContribution.order + 0.01

    use_ayon_entity_uri = False

    def process(self, instance):

        folder_path = instance.data["folderPath"]
        product_name = instance.data["productName"]
        self.log.debug(f"Building asset: {folder_path} > {product_name}")
        folder_name = folder_path.rsplit("/", 1)[-1]

        # Contribute layers to asset
        # Use existing asset and add to it, or initialize a new asset layer
        path = get_last_publish(instance)
        payload_layer = None
        if path and BUILD_INTO_LAST_VERSIONS:
            # If there's a payload file, put it in the payload instead
            folder = os.path.dirname(path)
            payload_path = os.path.join(folder, "payload.usd")
            if os.path.exists(payload_path):
                payload_layer = Sdf.Layer.OpenAsAnonymous(payload_path)

            asset_layer = Sdf.Layer.OpenAsAnonymous(path)
        else:
            # If no existing publish of this product exists then we initialize
            # the layer as either a default asset or shot structure.
            init_type = instance.data["contribution_target_product_init"]
            asset_layer, payload_layer = self.init_layer(
                asset_name=folder_name, init_type=init_type
            )

        # Author timeCodesPerSecond and framesPerSecond if the asset layer
        # is currently lacking any but our current context does specify an FPS
        fps = instance.data.get("fps", instance.context.data.get("fps"))
        if fps is not None:
            if (
                not asset_layer.HasTimeCodesPerSecond()
                    and not asset_layer.HasFramesPerSecond()
            ):
                # Author FPS on the asset layer since there is no opinion yet
                self.log.info("Authoring FPS on Asset Layer: %s FPS", fps)
                asset_layer.timeCodesPerSecond = fps
                asset_layer.framesPerSecond = fps

            if fps != asset_layer.timeCodesPerSecond:
                self.log.warning(
                    "Current instance FPS '%s' does not match asset layer "
                    "timecodes per second '%s'",
                    fps, asset_layer.timeCodesPerSecond
                )
            if fps != asset_layer.framesPerSecond:
                self.log.warning(
                    "Current instance FPS '%s' does not match asset layer "
                    "frames per second '%s'",
                    fps, asset_layer.framesPerSecond
                )

        target_layer = payload_layer if payload_layer else asset_layer

        # Get unique layer instances (remove duplicate entries)
        processed_ids = set()
        layer_instances = []
        for layer_inst in instance.data["source_instances"]:
            if layer_inst.id in processed_ids:
                continue
            layer_instances.append(layer_inst)
            processed_ids.add(layer_inst.id)

        # Insert the layer in contributions order
        def sort_by_order(instance):
            return instance.data["usd_layer_order"]

        for layer_instance in sorted(layer_instances,
                                     key=sort_by_order,
                                     reverse=True):

            layer_id = layer_instance.data["usd_layer_id"]
            order = layer_instance.data["usd_layer_order"]

            path = get_instance_uri_path(instance=layer_instance,
                                         resolve=not self.use_ayon_entity_uri)
            add_ordered_sublayer(target_layer,
                                 contribution_path=path,
                                 layer_id=layer_id,
                                 order=order,
                                 # Add the sdf argument metadata which allows
                                 # us to later detect whether another path
                                 # has the same layer id, so we can replace it.
                                 add_sdf_arguments_metadata=True)

        # Save the file
        staging_dir = self.staging_dir(instance)
        filename = f"{instance.name}.usd"
        filepath = os.path.join(staging_dir, filename)
        asset_layer.Export(filepath, args={"format": "usda"})

        add_representation(
            instance,
            name="usd",
            files=filename,
            staging_dir=staging_dir
        )

        if payload_layer:
            payload_path = os.path.join(staging_dir, "payload.usd")
            payload_layer.Export(payload_path, args={"format": "usda"})
            self.add_relative_file(instance, payload_path)

    def init_layer(self, asset_name, init_type):
        """Initialize layer if no previous version exists"""

        if init_type == "asset":
            asset_layer = Sdf.Layer.CreateAnonymous()
            created_layers = setup_asset_layer(asset_layer, asset_name,
                                               force_add_payload=True,
                                               set_payload_path=True)
            payload_layer = created_layers[0].layer
            return asset_layer, payload_layer

        elif init_type == "shot":
            shot_layer = Sdf.Layer.CreateAnonymous()
            set_layer_defaults(shot_layer, default_prim=None)
            return shot_layer, None

        else:
            raise ValueError(
                "USD Target Product contribution can only initialize "
                "as 'asset' or 'shot', got: '{}'".format(init_type)
            )

    def add_relative_file(self, instance, source, staging_dir=None):
        """Add transfer for a relative path form staging to publish dir.

        Unlike files in representations, the file will not be renamed and
        will be ingested one-to-one into the publish directory.

        Note: This file does not get registered as a representation, because
          representation files always get renamed by the publish template
          system. These files get included in the `representation["files"]`
          info with all the representations of the version - and thus will
          appear multiple times per version.

        """
        # TODO: It can be nice to force a particular representation no matter
        #  what to adhere to a certain filename on integration because e.g. a
        #  particular file format relies on that file named like that or alike
        #  and still allow regular registering with the database as a file of
        #  the version. As such we might want to tweak integrator logic?
        if staging_dir is None:
            staging_dir = self.staging_dir(instance)

        assert isinstance(staging_dir, str), "Staging dir must be string"
        publish_dir: str = instance.data["publishDir"]

        relative_path = os.path.relpath(source, staging_dir)
        destination = os.path.join(publish_dir, relative_path)
        destination = os.path.normpath(destination)

        transfers = instance.data.setdefault("transfers", [])
        self.log.debug(f"Adding relative file {source} -> {relative_path}")
        transfers.append((source, destination))
