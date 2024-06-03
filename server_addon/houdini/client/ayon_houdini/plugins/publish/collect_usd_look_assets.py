import re

import os
import glob
from typing import List, Optional
import dataclasses

import pyblish.api
import hou
from pxr import Sdf


# Colorspace attributes differ per renderer implementation in the USD data
# Some have dedicated input names like Arnold and Redshift, whereas others like
# MaterialX store `colorSpace` metadata on the asset property itself.
# See `get_colorspace` method on the plug-in for more details
COLORSPACE_ATTRS = [
    "inputs:color_space",        # Image Vop (arnold::image)
    "inputs:tex0_colorSpace",    # RS Texture Vop (redshift::TextureSampler)
    # TODO: USD UV Texture VOP doesn't seem to use colorspaces from the actual
    #  OCIO configuration so we skip these for now. Especially since the
    #  texture is usually used for 'preview' purposes anyway.
    # "inputs:sourceColorSpace",   # USD UV Texture Vop (usduvtexture::2.0)
]


@dataclasses.dataclass
class Resource:
    attribute: str            # property path
    source: str               # unresolved source path
    files: List[str]          # resolve list of files, e.g. multiple for <UDIM>
    color_space: str = None   # colorspace of the resource


def get_layer_property_paths(layer: Sdf.Layer) -> List[Sdf.Path]:
    """Return all property paths from a layer"""
    paths = []

    def collect_paths(path):
        if not path.IsPropertyPath():
            return
        paths.append(path)

    layer.Traverse("/", collect_paths)

    return paths


class CollectUsdLookAssets(pyblish.api.InstancePlugin):
    """Collect all assets introduced by the look.

    We are looking to collect e.g. all texture resources so we can transfer
    them with the publish and write then to the publish location.

    If possible, we'll also try to identify the colorspace of the asset.

    """
    # TODO: Implement $F frame support (per frame values)
    # TODO: If input image is already a published texture or resource than
    #   preferably we'd keep the link in-tact and NOT update it. We can just
    #   start ignoring AYON URIs

    label = "Collect USD Look Assets"
    order = pyblish.api.CollectorOrder
    hosts = ["houdini"]
    families = ["look"]

    exclude_suffixes = [".usd", ".usda", ".usdc", ".usdz", ".abc", ".vbd"]

    def process(self, instance):

        rop: hou.RopNode = hou.node(instance.data.get("instance_node"))
        if not rop:
            return

        lop_node: hou.LopNode = instance.data.get("output_node")
        if not lop_node:
            return

        above_break_layers = set(lop_node.layersAboveLayerBreak())

        stage = lop_node.stage()
        layers = [
            layer for layer
            in stage.GetLayerStack(includeSessionLayers=False)
            if layer.identifier not in above_break_layers
        ]

        instance_resources = self.get_layer_assets(layers)

        # Define a relative asset remapping for the USD Extractor so that
        # any textures are remapped to their 'relative' publish path.
        # All textures will be in a relative `./resources/` folder
        remap = {}
        for resource in instance_resources:
            source = resource.source
            name = os.path.basename(source)
            remap[os.path.normpath(source)] = f"./resources/{name}"
        instance.data["assetRemap"] = remap

        # Store resources on instance
        resources = instance.data.setdefault("resources", [])
        for resource in instance_resources:
            resources.append(dataclasses.asdict(resource))

        # Log all collected textures
        # Note: It is fine for a single texture to be included more than once
        # where even one of them does not have a color space set, but the other
        # does. For example, there may be a USD UV Texture just for a GL
        # preview material which does not specify an OCIO color
        # space.
        all_files = []
        for resource in instance_resources:
            all_files.append(f"{resource.attribute}:")

            for filepath in resource.files:
                if resource.color_space:
                    file_label = f"- {filepath} ({resource.color_space})"
                else:
                    file_label = f"- {filepath}"
                all_files.append(file_label)

        self.log.info(
            "Collected assets:\n{}".format(
                "\n".join(all_files)
            )
        )

    def get_layer_assets(self, layers: List[Sdf.Layer]) -> List[Resource]:
        # TODO: Correctly resolve paths using Asset Resolver.
        #       Preferably this would use one cached
        #       resolver context to optimize the path resolving.
        # TODO: Fix for timesamples - if timesamples, then `.default` might
        #       not be authored on the spec

        resources: List[Resource] = list()
        for layer in layers:
            for path in get_layer_property_paths(layer):

                spec = layer.GetAttributeAtPath(path)
                if not spec:
                    continue

                if spec.typeName != "asset":
                    continue

                asset: Sdf.AssetPath = spec.default
                base, ext = os.path.splitext(asset.path)
                if ext in self.exclude_suffixes:
                    continue

                filepath = asset.path.replace("\\", "/")

                # Expand <UDIM> to all files of the available files on disk
                # TODO: Add support for `<TILE>`
                # TODO: Add support for `<ATTR:name INDEX:name DEFAULT:value>`
                if "<UDIM>" in filepath.upper():
                    pattern = re.sub(
                        r"<UDIM>",
                        # UDIM is always four digits
                        "[0-9]" * 4,
                        filepath,
                        flags=re.IGNORECASE
                    )
                    files = glob.glob(pattern)
                else:
                    # Single file
                    files = [filepath]

                # Detect the colorspace of the input asset property
                colorspace = self.get_colorspace(spec)

                resource = Resource(
                    attribute=path.pathString,
                    source=asset.path,
                    files=files,
                    color_space=colorspace
                )
                resources.append(resource)

        # Sort by filepath
        resources.sort(key=lambda r: r.source)

        return resources

    def get_colorspace(self, spec: Sdf.AttributeSpec) -> Optional[str]:
        """Return colorspace for a Asset attribute spec.

        There is currently no USD standard on how colorspaces should be
        represented for shaders or asset properties - each renderer's material
        implementations seem to currently use their own way of specifying the
        colorspace on the shader. As such, this comes with some guesswork.

        Args:
            spec (Sdf.AttributeSpec): The asset type attribute to retrieve
                the colorspace for.

        Returns:
            Optional[str]: The colorspace for the given attribute, if any.

        """
        # TODO: Support Karma, V-Ray, Renderman texture colorspaces
        # Materialx image defines colorspace as custom info on the attribute
        if spec.HasInfo("colorSpace"):
            return spec.GetInfo("colorSpace")

        # Arnold materials define the colorspace as a separate primvar
        # TODO: Fix for timesamples - if timesamples, then `.default` might
        #       not be authored on the spec
        prim_path = spec.path.GetPrimPath()
        layer = spec.layer
        for name in COLORSPACE_ATTRS:
            colorspace_property_path = prim_path.AppendProperty(name)
            colorspace_spec = layer.GetAttributeAtPath(
                colorspace_property_path
            )
            if colorspace_spec and colorspace_spec.default:
                return colorspace_spec.default


class CollectUsdLookResourceTransfers(pyblish.api.InstancePlugin):
    """Define the publish direct file transfers for any found resources.

    This ensures that any source texture will end up in the published look
    in the `resourcesDir`.

    """
    label = "Collect USD Look Transfers"
    order = pyblish.api.CollectorOrder + 0.496
    hosts = ["houdini"]
    families = ["look"]

    def process(self, instance):

        resources_dir = instance.data["resourcesDir"]
        transfers = instance.data.setdefault("transfers", [])
        for resource in instance.data.get("resources", []):
            for src in resource["files"]:
                dest = os.path.join(resources_dir, os.path.basename(src))
                transfers.append((src, dest))
                self.log.debug("Registering transfer: %s -> %s", src, dest)
