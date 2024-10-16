import os

import pyblish.api

from ayon_core.pipeline import OptionalPyblishPluginMixin
from ayon_core.pipeline.publish.lib import get_instance_expected_output_path

try:
    from pxr import Sdf, UsdUtils
    HAS_USD_LIBS = True
except ImportError:
    HAS_USD_LIBS = False


RELATIVE_ANCHOR_PREFIXES = ("./", "../", ".\\", "..\\")


def get_drive(path) -> str:
    """Return disk drive from path"""
    return os.path.splitdrive(path)[0]


class USDOutputProcessorRemapToRelativePaths(pyblish.api.InstancePlugin,
                                             OptionalPyblishPluginMixin):
    """Remap all paths in a USD Layer to be relative to its published path"""

    label = "Process USD files to use relative paths"
    families = ["usd"]

    # Run just before the Integrator
    order = pyblish.api.IntegratorOrder - 0.01

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        # Skip instance if not marked for integration
        if not instance.data.get("integrate", True):
            return

        # Some hosts may not have USD libs available but can publish USD data.
        # For those we'll log a warning.
        if not HAS_USD_LIBS:
            self.log.warning(
                "Unable to process USD files to relative paths because "
                "`pxr` USD libraries could not be imported.")
            return

        # For each USD representation, process the file.
        for representation in instance.data.get("representations", []):
            representation: dict

            if representation.get("name") != "usd":
                continue

            # Get expected publish path
            published_path = get_instance_expected_output_path(
                instance,
                representation_name=representation["name"],
                ext=representation.get("ext")
            )
            published_path_root = os.path.dirname(published_path)

            # Process all files of the representation
            staging_dir: str = representation.get(
                "stagingDir", instance.data.get("stagingDir"))

            # Process single file or sequence of the representation
            if isinstance(representation["files"], str):
                # Single file
                fname: str = representation["files"]
                path = os.path.join(staging_dir, fname)
                self.process_usd(path, start=published_path_root)
            else:
                # Sequence
                for fname in representation["files"]:
                    path = os.path.join(staging_dir, fname)
                    self.process_usd(path, start=published_path_root)

        # Some instance may have additional transferred files which
        # themselves are not a representation. For those we need to look in
        # the `instance.data["transfers"]`
        for src, dest in instance.data.get("transfers", []):
            if not dest.endswith(".usd"):
                continue

            # Process USD file at `src` and turn all paths relative to
            # the `dest` path the file will end up at.
            dest_root = os.path.dirname(dest)
            self.process_usd(src, start=dest_root)

    def process_usd(self, usd_path, start):
        """Process a USD layer making all paths relative to `start`"""
        self.log.debug(f"Processing '{usd_path}'")
        layer = Sdf.Layer.FindOrOpen(usd_path)

        def modify_fn(asset_path: str):
            """Make all absolute non-anchored paths relative to `start`"""
            self.log.debug(f"Processing asset path: {asset_path}")

            # Do not touch paths already anchored paths
            if not os.path.isabs(asset_path):
                return asset_path

            # Do not touch paths already anchored paths
            if asset_path.startswith(RELATIVE_ANCHOR_PREFIXES):
                # Already anchored
                return asset_path

            # Do not touch what we know are AYON URIs
            if asset_path.startswith(("ayon://", "ayon+entity://")):
                return asset_path

            # Consider only files on the same drive, because otherwise no
            # 'relative' path exists for the file.
            if get_drive(start) != get_drive(asset_path):
                # Log a warning if different drive
                self.log.warning(
                    f"USD Asset Path '{asset_path}' can not be made relative"
                    f" to '{start}' because they are not on the same drive.")
                return asset_path

            anchored_path = "./" + os.path.relpath(asset_path, start)
            self.log.debug(f"Anchored path: {anchored_path}")
            return anchored_path

        # Get all "asset path" specs, sublayer paths and references/payloads.
        # Make all the paths relative.
        UsdUtils.ModifyAssetPaths(layer, modify_fn)
        if layer.dirty:
            layer.Save()
