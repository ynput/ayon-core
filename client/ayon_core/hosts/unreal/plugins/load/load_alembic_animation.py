# -*- coding: utf-8 -*-
"""Load Alembic Animation."""

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


class AnimationAlembicLoader(UnrealBaseLoader):
    """Load Unreal SkeletalMesh from Alembic"""

    product_types = {"animation"}
    label = "Import Alembic Animation"
    representations = ["abc"]
    icon = "cube"
    color = "orange"

    @staticmethod
    def _import_abc_task(
        filename, destination_path, destination_name, replace,
        default_conversion
    ):
        conversion = (
            None
            if default_conversion
            else {
                "flip_u": False,
                "flip_v": False,
                "rotation": [0.0, 0.0, 0.0],
                "scale": [1.0, 1.0, -1.0],
            }
        )

        params = {
            "filename": filename,
            "destination_path": destination_path,
            "destination_name": destination_name,
            "replace_existing": replace,
            "automated": True,
            "save": True,
            "options_properties": [
                ['import_type', 'unreal.AlembicImportType.SKELETAL']
            ],
            "conversion_settings": conversion
        }

        send_request("import_abc_task", params=params)

    def load(self, context, name=None, namespace=None, options=None):
        """Load and containerise representation into Content Browser.

        This is two step process. First, import FBX to temporary path and
        then call `containerise()` on it - this moves all content to new
        directory and then it will create AssetContainer there and imprint it
        with metadata. This will mark this path as container.

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

        # Create directory for asset and ayon container
        root = AYON_ASSET_DIR
        folder_name = context["folder"]["name"]
        folder_path = context["folder"]["path"]
        product_type = context["product"]["productType"]
        asset_name = f"{folder_name}_{name}" if folder_name else f"{name}"
        version = context["version"]["version"]

        asset_dir, container_name = send_request(
            "create_unique_asset_name", params={
                "root": root,
                "folder_name": folder_name,
                "name": name,
                "version": version})

        default_conversion = options.get("default_conversion") or False

        if not send_request(
                "does_directory_exist", params={"directory_path": asset_dir}):
            send_request(
                "make_directory", params={"directory_path": asset_dir})

            self._import_abc_task(
                self.fname, asset_dir, asset_name, False, default_conversion)

        data = {
            "schema": "ayon:container-2.0",
            "id": AYON_CONTAINER_ID,
            "folder_path": folder_path,
            "namespace": asset_dir,
            "container_name": container_name,
            "asset_name": asset_name,
            "loader": self.__class__.__name__,
            "representation_id": str(context["representation"]["id"]),
            "version_id": str(context["representation"]["versionId"]),
            "default_conversion": default_conversion,
            "product_type": product_type,
            # TODO these should be probably removed
            "asset": folder_path,
            "family": product_type,
        }

        containerise(asset_dir, container_name, data)

        return send_request(
            "list_assets", params={
                "directory_path": asset_dir,
                "recursive": True,
                "include_folder": True})

    def update(self, container, context):
        repre_entity = context["representation"]
        filename = get_representation_path(repre_entity)
        asset_dir = container["namespace"]
        asset_name = container["asset_name"]

        default_conversion = container["default_conversion"]

        self._import_abc_task(
            filename, asset_dir, asset_name, True, default_conversion)

        super(UnrealBaseLoader, self).update(container, context)
