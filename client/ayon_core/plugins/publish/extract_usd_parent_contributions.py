from __future__ import annotations
import os
import copy
from typing import Optional, Any

import pyblish.api

from ayon_core.lib import filter_profiles
from ayon_core.pipeline import publish

from ayon_core.pipeline.entity_uri import (
    construct_ayon_entity_uri,
    parse_ayon_entity_uri,
)
from ayon_core.pipeline.load.utils import get_representation_path_by_names
import ayon_api

try:
    from ayon_core.pipeline.usdlib import (
        BaseContribution,
        SublayerContribution,
        ReferenceContribution,
        VariantContribution,
        get_standard_default_prim_name,
)
except ImportError:
    pass


def resolve_entity_uri(entity_uri: str) -> str:
    """Resolve AYON entity URI to a filesystem path for local system."""
    response = ayon_api.post(
        "resolve",
        resolveRoots=True,
        uris=[entity_uri]
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Unable to resolve AYON entity URI filepath for "
            f"'{entity_uri}': {response.text}"
        )

    entities = response.data[0]["entities"]
    if len(entities) != 1:
        raise RuntimeError(
            f"Unable to resolve AYON entity URI '{entity_uri}' to a "
            f"single filepath. Received data: {response.data}"
        )
    return entities[0]["filePath"]


def find_nearest_parent_folder_of_type(
    project_name: str,
    source_folder_path: str,
    folder_types: set[str]
) -> list[dict]:
    """Find the nearest parent folder of a specific folder type, e.g. "sequence" or "global"

    Args:
        project_name (str): Name of the project.
        source_folder_path (str): The folder path from which to start searching.
        folder_types (set[str]): A set of parent folder types to look for.

    Returns:
        list[dict]: Nearest parent folder of each provided folder type.
    """
    parents = source_folder_path.split("/")

    # Parent paths
    parent_folder_paths = set()
    for i in range(len(parents)):
        parent = "/".join(parents[:i+1])
        parent_folder_paths.add(parent)

    # Get all parents,      sorted by depth
    parent_folders = sorted(
        ayon_api.get_folders(
            project_name=project_name,
            folder_paths=parent_folder_paths,
            folder_types=folder_types,
        ),
        key=lambda x: len(x["path"])
    )
    # Then populate a dict by folder type, lowest in hierarchy is added last
    # and hence is the only remaining entry of that type
    parent_folders_by_type = {
        parent_folder["folderType"]: parent_folder
        for parent_folder in parent_folders
    }
    return list(parent_folders_by_type.values())


class CollectUSDAssetContributions(pyblish.api.InstancePlugin,
                                   publish.AYONPyblishPluginMixin):
    """Add configurable USD contributions to the target instance.

    Allows to automatically contribute additional files on publish to a
    particular USD layer, using profiles-based filtering to define which
    contributions should be added to which products.
    """
    # Run late during collecting, because other collectors should not be
    # dependent on this.
    order = pyblish.api.CollectorOrder + 0.4999
    label = "Collect USD Custom Contributions"
    families = ["usdAsset"]
    enabled = True
    settings_category = "core"

    profiles: list[dict[str, Any]] = []

    def process(self, instance: pyblish.api.Instance):
        if not self.profiles:
            return

        profile = filter_profiles(
            self.profiles,
            {
                "task_types": instance.context.data["taskType"],
                "product_names": instance.data["productName"],
            }
        )
        if not profile:
            return

        contributions: list[BaseContribution] = instance.data.setdefault(
            "usd_contributions", []
        )
        for contribution_settings in profile["contributions"]:
            contribution = self._get_contribution(
                contribution_settings=contribution_settings,
                instance=instance,
            )
            if contribution:
                self.log.debug(f"Adding contribution: {contribution}")
                contributions.append(contribution)

    def _get_contribution(
            self,
            contribution_settings: dict,
            instance: pyblish.api.Instance,
    ) -> Optional[BaseContribution]:
        """Get contribution based on the provided settings."""

        # Get the source filepath for the contribution
        source: str = self._get_source(contribution_settings, instance)
        if not source:
            return None

        # Skip if not exists and the source must exist
        if (
                contribution_settings["only_if_existing"]
                and not self._source_exists(source)
        ):
            self.log.info(
                f"Contribution source does not exist,"
                f" skipping contribution: {source}"
            )
            return None

        # Construct the contribution
        layer_id: str = contribution_settings["name"]
        order: int = contribution_settings["order"]
        layer_type: str = contribution_settings["type"]
        if layer_type == "sublayer":
            return SublayerContribution(
                source=source,
                order=order,
                layer_id=layer_id,
            )
        elif layer_type == "reference":
            reference_settings: dict = contribution_settings["reference"]
            prim_path = self._format_prim_path(
                reference_settings["prim_path"],
                instance,
            )
            return ReferenceContribution(
                source=source,
                order=order,
                layer_id=layer_id,
                target_prim_path=prim_path,
            )
        elif layer_type == "variant":
            variant_settings: dict = contribution_settings["variant"]
            variant_is_default: bool = (
                True
                if variant_settings["variant_is_default"] == "yes"
                else False
            )
            prim_path = self._format_prim_path(
                variant_settings["prim_path"],
                instance,
            )
            return VariantContribution(
                source=source,
                order=order,
                layer_id=layer_id,
                target_prim_path=prim_path,
                variant_set_name=variant_settings["variant_set_name"],
                variant_name=variant_settings["variant_name"],
                variant_is_default=variant_is_default,
            )
        else:
            raise ValueError(f"Unknown layer type: {layer_type}")

    def _get_source(
        self,
        contribution_settings: dict,
        instance: pyblish.api.Instance,
    ) -> Optional[str]:
        source_type: str = contribution_settings["load_from"]
        if source_type == "source_path":
            source: str = contribution_settings["source_path"]
            return source.format_map(instance.data["anatomyData"])
        elif source_type == "product":
            return self._search_product(instance, contribution_settings)
        else:
            raise ValueError(f"Unknown contribution source type: {source_type}")

    def _format_prim_path(
        self,
        prim_path: str,
        instance: pyblish.api.Instance
    ) -> str:
        """Allow formatting the prim path using some dynamic keys based on the
        instance data, e.g. default prim name based on folder"""
        template_data = copy.deepcopy(instance.data["anatomyData"])
        template_data["default_prim_path"] = (
            get_standard_default_prim_name(instance.data["folderPath"])
        )
        return prim_path.format_map(template_data)

    def _search_product(
        self,
        contribution_settings: dict,
        instance: pyblish.api.Instance,
    ) -> Optional[str]:
        # Get from settings
        search_settings: dict = contribution_settings["search_product"]
        parent_folder_type: str = search_settings["folder_type"]
        product_name: str = search_settings["product_name"]
        version_name: str = search_settings["version"]
        representation_name: str = search_settings["representation_name"]

        # Find the nearest parent folder of a specific folder type, e.g.
        # "sequence" or "global"
        project_name: str = instance.context.data["projectName"]
        folder_path: str = instance.data["folderPath"]
        nearest_parent_folders = find_nearest_parent_folder_of_type(
            project_name=project_name,
            source_folder_path=folder_path,
            folder_types={parent_folder_type}
        )
        parent_folder = next(iter(nearest_parent_folders), None)
        if not parent_folder:
            self.log.debug(
                f"No parent folder of type '{parent_folder_type}' found for"
                f" folder '{folder_path}', skipping..."
            )
            return None

        self.log.debug(
            f"Found parent folder of type '{parent_folder_type}':"
            f" {parent_folder['path']}"
        )
        as_ayon_entity_uri: bool = search_settings["as_ayon_entity_uri"]
        if as_ayon_entity_uri:
            return construct_ayon_entity_uri(
                project_name=project_name,
                folder_path=folder_path,
                product=product_name,
                version=version_name,
                representation_name=representation_name,
            )
        return get_representation_path_by_names(
            project_name=project_name,
            folder_path=parent_folder["path"],
            product_name=product_name,
            version_name=version_name,
            representation_name=representation_name,
            anatomy=instance.context.data["anatomy"],
        )

    def _source_exists(self, source: str) -> bool:
        # TODO: Allow actual USD Resolve() call to resolve source path as well,
        #  which may be helpful when dealing with custom USD resolver.
        if parse_ayon_entity_uri(source):
            source = resolve_entity_uri(source)
        return os.path.isfile(source)
