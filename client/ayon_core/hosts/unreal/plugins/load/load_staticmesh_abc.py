# -*- coding: utf-8 -*-
"""Loader for Static Mesh alembics."""

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


class StaticMeshAlembicLoader(UnrealBaseLoader):
    """Load Unreal StaticMesh from Alembic"""

    product_types = {"model", "staticMesh"}
    label = "Import Alembic Static Mesh"
    representations = ["abc"]
    icon = "cube"
    color = "orange"

    root = AYON_ASSET_DIR

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
                "scale": [1.0, 1.0, 1.0],
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
                ['import_type', 'unreal.AlembicImportType.STATIC_MESH']
            ],
            "sub_options_properties": [
                ["static_mesh_settings", "merge_meshes", "True"]
            ],
            "conversion_settings": conversion
        }

        send_request("import_abc_task", params=params)

    def load(self, context, name=None, namespace=None, options=None):
        """Load and containerise representation into Content Browser.

        Args:
            context (dict): application context
            name (str): Product name
            namespace (str): in Unreal this is basically path to container.
                             This is not passed here, so namespace is set
                             by `containerise()` because only then we know
                             real path.
            data (dict): Those would be data to be imprinted.

        Returns:
            list(str): list of container content

        """
        # Create directory for asset and Ayon container
        root = AYON_ASSET_DIR
        folder_path = context["folder"]["path"]
        folder_name = context["folder"]["name"]
        if options and options.get("asset_dir"):
            root = options["asset_dir"]
        asset_name = f"{folder_name}_{name}" if folder_name else f"{name}"
        version = context["version"]["version"]

        # Check if version is hero version and use different name
        name_version = (
            f"{name}_hero" if version < 0 else f"{name}_v{version:03d}"
        )
        asset_dir, container_name = send_request(
            "create_unique_asset_name", params={
                "root": root,
                "folder_name": folder_name,
                "name": name_version})

        default_conversion = options.get("default_conversion") or False

        if not send_request(
                "does_directory_exist", params={"directory_path": asset_dir}):
            send_request(
                "make_directory", params={"directory_path": asset_dir})

            self._import_abc_task(
                self.fname, asset_dir, asset_name, False, default_conversion)

        product_type = context["product"]["productType"]

        data = {
            "schema": "ayon:container-2.0",
            "id": AYON_CONTAINER_ID,
            "namespace": asset_dir,
            "container_name": container_name,
            "asset_name": asset_name,
            "loader": self.__class__.__name__,
            "representation": str(context["representation"]["_id"]),
            "parent": str(context["representation"]["parent"]),
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
