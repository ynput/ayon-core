# -*- coding: utf-8 -*-
"""Loader for published alembics."""

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


class PointCacheAlembicLoader(UnrealBaseLoader):
    """Load Point Cache from Alembic"""

    product_types = {"model", "pointcache"}
    label = "Import Alembic Point Cache"
    representations = {"abc"}
    icon = "cube"
    color = "orange"

    @staticmethod
    def _import_abc_task(
        filename, destination_path, destination_name, replace,
        frame_start, frame_end, default_conversion
    ):
        conversion = (
            None
            if default_conversion
            else {
                "flip_u": False,
                "flip_v": True,
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
                ["import_type", "unreal.AlembicImportType.GEOMETRY_CACHE"]
            ],
            "sub_options_properties": [
                ["geometry_cache_settings", "flatten_tracks", "False"],
                ["sampling_settings", "frame_start", str(frame_start)],
                ["sampling_settings", "frame_end", str(frame_end)]
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
            options (dict): Those would be data to be imprinted. This is not
                            used now, data are imprinted by `containerise()`.
        """
        # Create directory for asset and Ayon container
        root = AYON_ASSET_DIR
        folder_entity = context["folder"]
        folder_path = folder_entity["path"]
        folder_name = folder_entity["name"]
        folder_attributes = folder_entity["attrib"]
        asset_name = f"{folder_name}_{name}" if folder_name else f"{name}"

        default_conversion = options.get("default_conversion") or False

        # Check if version is hero version and use different name
        version = context["version"]["version"]
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

            frame_start = folder_attributes.get("frameStart")
            frame_end = folder_attributes.get("frameEnd")

            # If frame start and end are the same, we increase the end frame by
            # one, otherwise Unreal will not import it
            if frame_start == frame_end:
                frame_end += 1

            self._import_abc_task(
                self.fname, asset_dir, asset_name, False,
                frame_start, frame_end, default_conversion)

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
            "frame_start": frame_start,
            "frame_end": frame_end,
            "product_type": product_type,
            "folder_path": folder_path,
            "default_conversion": default_conversion,
            # TODO these should be probably removed
            "family": product_type,
            "asset": folder_path,
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
