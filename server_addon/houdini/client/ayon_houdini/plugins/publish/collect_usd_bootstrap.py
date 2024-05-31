import pyblish.api
import ayon_api
from ayon_core.pipeline import usdlib, KnownPublishError

from ayon_houdini.api import plugin

class CollectUsdBootstrap(plugin.HoudiniInstancePlugin):
    """Collect special Asset/Shot bootstrap instances if those are needed.

    Some specific products are intended to be part of the default structure
    of an "Asset" or "Shot" in our USD pipeline. For example, for an Asset
    we layer a Model and Shade USD file over each other and expose that in
    a Asset USD file, ready to use.

    On the first publish of any of the components of a Asset or Shot the
    missing pieces are bootstrapped and generated in the pipeline too. This
    means that on the very first publish of your model the Asset USD file
    will exist too.

    """

    order = pyblish.api.CollectorOrder + 0.35
    label = "Collect USD Bootstrap"
    families = ["usd", "usd.layered"]

    def process(self, instance):

        # Detect whether the current product is a product in a pipeline
        def get_bootstrap(instance):
            instance_product_name = instance.data["productName"]
            for name, layers in usdlib.PIPELINE.items():
                if instance_product_name in set(layers):
                    return name  # e.g. "asset"
            else:
                return

        bootstrap = get_bootstrap(instance)
        if bootstrap:
            self.add_bootstrap(instance, bootstrap)

        # Check if any of the dependencies requires a bootstrap
        for dependency in instance.data.get("publishDependencies", list()):
            bootstrap = get_bootstrap(dependency)
            if bootstrap:
                self.add_bootstrap(dependency, bootstrap)

    def add_bootstrap(self, instance, bootstrap):

        self.log.debug("Add bootstrap for: %s" % bootstrap)

        project_name = instance.context.data["projectName"]
        folder_path = instance.data["folderPath"]
        folder_name = folder_path.rsplit("/", 1)[-1]
        folder_entity = ayon_api.get_folder_by_path(project_name, folder_path)
        if not folder_entity:
            raise KnownPublishError(
                "Folder '{}' does not exist".format(folder_path)
            )

        # Check which are not about to be created and don't exist yet
        required = {"shot": ["usdShot"], "asset": ["usdAsset"]}.get(bootstrap)

        require_all_layers = instance.data.get("requireAllLayers", False)
        if require_all_layers:
            # USD files load fine in usdview and Houdini even when layered or
            # referenced files do not exist. So by default we don't require
            # the layers to exist.
            layers = usdlib.PIPELINE.get(bootstrap)
            if layers:
                required += list(layers)

        self.log.debug("Checking required bootstrap: %s" % required)
        for product_name in required:
            if self._product_exists(
                project_name, instance, product_name, folder_entity
            ):
                continue

            self.log.debug(
                "Creating {0} USD bootstrap: {1} {2}".format(
                    bootstrap, folder_path, product_name
                )
            )

            product_type = "usd.bootstrap"
            new = instance.context.create_instance(product_name)
            new.data["productName"] = product_name
            new.data["label"] = "{0} ({1})".format(product_name, folder_name)
            new.data["productType"] = product_type
            new.data["family"] = product_type
            new.data["comment"] = "Automated bootstrap USD file."
            new.data["publishFamilies"] = ["usd"]

            # Do not allow the user to toggle this instance
            new.data["optional"] = False

            # Copy some data from the instance for which we bootstrap
            for key in ["folderPath"]:
                new.data[key] = instance.data[key]

    def _product_exists(
        self, project_name, instance, product_name, folder_entity
    ):
        """Return whether product exists in current context or in database."""
        # Allow it to be created during this publish session
        context = instance.context

        folder_path = folder_entity["path"]
        for inst in context:
            if (
                inst.data["productName"] == product_name
                and inst.data["folderPath"] == folder_path
            ):
                return True

        # Or, if they already exist in the database we can
        # skip them too.
        if ayon_api.get_product_by_name(
            project_name, product_name, folder_entity["id"], fields={"id"}
        ):
            return True
        return False
