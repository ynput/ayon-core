# -*- coding: utf-8 -*-
"""Load UAsset."""
from pathlib import Path
import shutil

from ayon_core.pipeline import (
    get_representation_path,
    AYON_CONTAINER_ID
)
from ayon_core.hosts.unreal.api.plugin import UnrealBaseLoader
from ayon_core.hosts.unreal.api.pipeline import (
    send_request,
    containerise,
    AYON_ASSET_DIR,
)


class UAssetLoader(UnrealBaseLoader):
    """Load UAsset."""

    product_types = {"uasset"}
    label = "Load UAsset"
    representations = ["uasset"]
    icon = "cube"
    color = "orange"

    extension = "uasset"

    def load(self, context, name=None, namespace=None, options=None):
        """Load and containerise representation into Content Browser.

        Args:
            context (dict): application context
            name (str): Product name
            namespace (str): in Unreal this is basically path to container.
                             This is not passed here, so namespace is set
                             by `containerise()` because only then we know
                             real path.
            options (dict): Those would be data to be imprinted. This is not
                            used now, data are imprinted by `containerise()`.
        """

        # Create directory for asset and Ayon container
        root = AYON_ASSET_DIR
        folder_path = context["folder"]["path"]
        folder_name = context["folder"]["name"]
        suffix = "_CON"
        asset_name = f"{folder_name}_{name}" if folder_name else f"{name}"

        asset_dir, container_name = send_request(
            "create_unique_asset_name", params={
                "root": root,
                "folder_name": folder_name,
                "name": name})

        unique_number = 1
        while send_request(
                "does_directory_exist",
                params={"directory_path": f"{asset_dir}_{unique_number:02}"}):
            unique_number += 1

        asset_dir = f"{asset_dir}_{unique_number:02}"
        container_name = f"{container_name}_{unique_number:02}{suffix}"

        send_request(
            "make_directory", params={"directory_path": asset_dir})

        project_content_dir = send_request("project_content_dir")
        destination_path = asset_dir.replace(
            "/Game", Path(project_content_dir).as_posix(), 1)

        path = self.filepath_from_context(context)
        shutil.copy(
            path,
            f"{destination_path}/{name}_{unique_number:02}.{self.extension}")

        product_type = context["product"]["productType"]
        data = {
            "schema": "ayon:container-2.0",
            "id": AYON_CONTAINER_ID,
            "namespace": asset_dir,
            "folder_path": folder_path,
            "container_name": container_name,
            "asset_name": asset_name,
            "loader": self.__class__.__name__,
            "representation": str(context["representation"]["id"]),
            "parent": str(context["representation"]["versionId"]),
            "product_type": product_type,
            # TODO these should be probably removed
            "asset": folder_path,
            "family": product_type
        }

        containerise(asset_dir, container_name, data)

        return send_request(
            "list_assets", params={
                "directory_path": asset_dir,
                "recursive": True,
                "include_folder": True})

    def update(self, container, context):
        asset_dir = container["namespace"]

        product_name = context["product"]["name"]
        repre_entity = context["representation"]

        unique_number = container["container_name"].split("_")[-2]

        project_content_dir = send_request("project_content_dir")
        destination_path = asset_dir.replace(
            "/Game", Path(project_content_dir).as_posix(), 1)

        send_request(
            "delete_assets_in_dir_but_container",
            params={"asset_dir": asset_dir})

        update_filepath = get_representation_path(repre_entity)

        shutil.copy(
            update_filepath,
            f"{destination_path}/{product_name}_{unique_number}.{self.extension}"
        )

        super(UAssetLoader, self).update(container, context)


class UMapLoader(UAssetLoader):
    """Load Level."""

    product_types = {"uasset"}
    label = "Load Level"
    representations = ["umap"]

    extension = "umap"
