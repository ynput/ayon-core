import os
import sys
import subprocess
import collections
from typing import Optional, Any

from ayon_core.pipeline.load import get_representation_path_with_anatomy
from ayon_core.pipeline.actions import (
    LoaderActionPlugin,
    LoaderActionItem,
    LoaderActionSelection,
    LoaderActionResult,
)


def open_file(filepath: str) -> None:
    """Open file with system default executable"""
    if sys.platform.startswith("darwin"):
        subprocess.call(("open", filepath))
    elif os.name == "nt":
        os.startfile(filepath)
    elif os.name == "posix":
        subprocess.call(("xdg-open", filepath))


class OpenFileAction(LoaderActionPlugin):
    """Open Image Sequence or Video with system default"""
    identifier = "core.open-file"

    product_types = {"render2d"}

    def get_action_items(
        self, selection: LoaderActionSelection
    ) -> list[LoaderActionItem]:
        repres = []
        if selection.selected_type == "representation":
            repres = selection.entities.get_representations(
                selection.selected_ids
            )

        if selection.selected_type == "version":
            repres = selection.entities.get_versions_representations(
                selection.selected_ids
            )

        if not repres:
            return []

        repre_ids = {repre["id"] for repre in repres}
        versions = selection.entities.get_representations_versions(
            repre_ids
        )
        product_ids = {version["productId"] for version in versions}
        products = selection.entities.get_products(product_ids)
        filtered_product_ids = {
            product["id"]
            for product in products
            if product["productType"] in self.product_types
        }
        if not filtered_product_ids:
            return []

        versions_by_product_id = collections.defaultdict(list)
        for version in versions:
            versions_by_product_id[version["productId"]].append(version)

        repres_by_version_ids = collections.defaultdict(list)
        for repre in repres:
            repres_by_version_ids[repre["versionId"]].append(repre)

        filtered_repres = []
        for product_id in filtered_product_ids:
            for version in versions_by_product_id[product_id]:
                for repre in repres_by_version_ids[version["id"]]:
                    filtered_repres.append(repre)

        repre_ids_by_name = collections.defaultdict(set)
        for repre in filtered_repres:
            repre_ids_by_name[repre["name"]].add(repre["id"])

        return [
            LoaderActionItem(
                identifier="open-file",
                label=repre_name,
                group_label="Open file",
                order=-10,
                data={"representation_ids": list(repre_ids)},
                icon={
                    "type": "material-symbols",
                    "name": "play_circle",
                    "color": "#FFA500",
                }
            )
            for repre_name, repre_ids in repre_ids_by_name.items()
        ]

    def execute_action(
        self,
        identifier: str,
        selection: LoaderActionSelection,
        data: dict[str, Any],
        form_values: dict[str, Any],
    ) -> Optional[LoaderActionResult]:
        path = None
        repre_path = None
        repre_ids = data["representation_ids"]
        for repre in selection.entities.get_representations(repre_ids):
            repre_path = get_representation_path_with_anatomy(
                repre, selection.get_project_anatomy()
            )
            if os.path.exists(repre_path):
                path = repre_path
                break

        if path is None:
            if repre_path is None:
                return LoaderActionResult(
                    "Failed to fill representation path...",
                    success=False,
                )
            return LoaderActionResult(
                "File to open was not found...",
                success=False,
            )

        self.log.info(f"Opening: {path}")
        open_file(path)

        return LoaderActionResult(
            "File was opened...",
            success=True,
        )
