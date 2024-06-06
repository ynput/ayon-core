# -*- coding: utf-8 -*-
"""Load Skeletal Meshes form FBX."""

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


class SkeletalMeshFBXLoader(UnrealBaseLoader):
    """Load Unreal SkeletalMesh from FBX."""

    product_types = {"rig", "skeletalMesh"}
    label = "Import FBX Skeletal Mesh"
    representations = ["fbx"]
    icon = "cube"
    color = "orange"

    @staticmethod
    def _import_fbx_task(
        filename, destination_path, destination_name, replace
    ):
        params = {
            "filename": filename,
            "destination_path": destination_path,
            "destination_name": destination_name,
            "replace_existing": replace,
            "automated": True,
            "save": True,
            "options_properties": [
                ["import_animations", "False"],
                ["import_mesh", "True"],
                ["import_materials", "False"],
                ["import_textures", "False"],
                ["skeleton", "None"],
                ["create_physics_asset", "False"],
                ["mesh_type_to_import",
                 "unreal.FBXImportType.FBXIT_SKELETAL_MESH"]
            ],
            "sub_options_properties": [
                [
                    "skeletal_mesh_import_data",
                    "import_content_type",
                    "unreal.FBXImportContentType.FBXICT_ALL"
                ],
                [
                    "skeletal_mesh_import_data",
                    "normal_import_method",
                    "unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS"
                ]
            ]
        }

        send_request("import_fbx_task", params=params)

    def load(self, context, name=None, namespace=None, options=None):
        """Load and containerise representation into Content Browser.

        This is a two step process. First, import FBX to temporary path and
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
        # Create directory for asset and OpenPype container
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

        if not send_request(
                "does_directory_exist", params={"directory_path": asset_dir}):
            send_request(
                "make_directory", params={"directory_path": asset_dir})

            self._import_fbx_task(self.fname, asset_dir, asset_name, False)

        product_type = context["product"]["productType"]

        data = {
            "schema": "ayon:container-2.0",
            "id": AYON_CONTAINER_ID,
            "namespace": asset_dir,
            "container_name": container_name,
            "asset_name": asset_name,
            "loader": self.__class__.__name__,
            "representation": str(context["representation"]["id"]),
            "parent": str(context["representation"]["versionId"]),
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

        self._import_fbx_task(filename, asset_dir, asset_name, True)

        super(UnrealBaseLoader, self).update(container, context)
