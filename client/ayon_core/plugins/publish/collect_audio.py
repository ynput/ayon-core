import collections
import pyblish.api

from ayon_core.client import (
    get_assets,
    get_subsets,
    get_last_versions,
    get_representations,
    get_asset_name_identifier,
)
from ayon_core.pipeline.load import get_representation_path_with_anatomy


class CollectAudio(pyblish.api.ContextPlugin):
    """Collect asset's last published audio.

    The audio product name searched for is defined in:
        project settings > Collect Audio

    Note:
        The plugin was instance plugin but because of so much queries the
            plugin was slowing down whole collection phase a lot thus was
            converted to context plugin which requires only 4 queries top.
    """

    label = "Collect Asset Audio"
    order = pyblish.api.CollectorOrder + 0.1
    families = ["review"]
    hosts = [
        "nuke",
        "maya",
        "shell",
        "hiero",
        "premiere",
        "harmony",
        "traypublisher",
        "fusion",
        "tvpaint",
        "resolve",
        "webpublisher",
        "aftereffects",
        "flame",
        "unreal"
    ]

    audio_product_name = "audioMain"

    def process(self, context):
        # Fake filtering by family inside context plugin
        filtered_instances = []
        for instance in pyblish.api.instances_by_plugin(
            context, self.__class__
        ):
            # Skip instances that already have audio filled
            if instance.data.get("audio"):
                self.log.debug(
                    "Skipping Audio collection. It is already collected"
                )
                continue
            filtered_instances.append(instance)

        # Skip if none of instances remained
        if not filtered_instances:
            return

        # Add audio to instance if exists.
        instances_by_asset_name = collections.defaultdict(list)
        for instance in filtered_instances:
            asset_name = instance.data["folderPath"]
            instances_by_asset_name[asset_name].append(instance)

        asset_names = set(instances_by_asset_name.keys())
        self.log.debug((
            "Searching for audio product '{product}' in assets {assets}"
        ).format(
            product=self.audio_product_name,
            assets=", ".join([
                '"{}"'.format(asset_name)
                for asset_name in asset_names
            ])
        ))

        # Query all required documents
        project_name = context.data["projectName"]
        anatomy = context.data["anatomy"]
        repre_docs_by_asset_names = self.query_representations(
            project_name, asset_names)

        for asset_name, instances in instances_by_asset_name.items():
            repre_docs = repre_docs_by_asset_names[asset_name]
            if not repre_docs:
                continue

            repre_doc = repre_docs[0]
            repre_path = get_representation_path_with_anatomy(
                repre_doc, anatomy
            )
            for instance in instances:
                instance.data["audio"] = [{
                    "offset": 0,
                    "filename": repre_path
                }]
                self.log.debug("Audio Data added to instance ...")

    def query_representations(self, project_name, folder_paths):
        """Query representations related to audio products for passed assets.

        Args:
            project_name (str): Project in which we're looking for all
                entities.
            folder_paths (Iterable[str]): Folder paths where to look for audio
                products and their representations.

        Returns:
            collections.defaultdict[str, List[Dict[Str, Any]]]: Representations
                related to audio products by asset name.
        """

        output = collections.defaultdict(list)
        # Query asset documents
        asset_docs = get_assets(
            project_name,
            asset_names=folder_paths,
            fields=["_id", "name", "data.parents"]
        )

        folder_id_by_path = {
            get_asset_name_identifier(asset_doc): asset_doc["_id"]
            for asset_doc in asset_docs
        }
        folder_ids = set(folder_id_by_path.values())

        # Query products with name define by 'audio_product_name' attr
        # - one or none products with the name should be available on an asset
        subset_docs = get_subsets(
            project_name,
            subset_names=[self.audio_product_name],
            asset_ids=folder_ids,
            fields=["_id", "parent"]
        )
        product_id_by_folder_id = {}
        for subset_doc in subset_docs:
            folder_id = subset_doc["parent"]
            product_id_by_folder_id[folder_id] = subset_doc["_id"]

        product_ids = set(product_id_by_folder_id.values())
        if not product_ids:
            return output

        # Find all latest versions for the products
        version_docs_by_product_id = get_last_versions(
            project_name, subset_ids=product_ids, fields=["_id", "parent"]
        )
        version_id_by_product_id = {
            product_id: version_doc["_id"]
            for product_id, version_doc in version_docs_by_product_id.items()
        }
        version_ids = set(version_id_by_product_id.values())
        if not version_ids:
            return output

        # Find representations under latest versions of audio products
        repre_docs = get_representations(
            project_name, version_ids=version_ids
        )
        repre_docs_by_version_id = collections.defaultdict(list)
        for repre_doc in repre_docs:
            version_id = repre_doc["parent"]
            repre_docs_by_version_id[version_id].append(repre_doc)

        if not repre_docs_by_version_id:
            return output

        for folder_path in folder_paths:
            folder_id = folder_id_by_path.get(folder_path)
            product_id = product_id_by_folder_id.get(folder_id)
            version_id = version_id_by_product_id.get(product_id)
            output[folder_path] = repre_docs_by_version_id[version_id]
        return output
