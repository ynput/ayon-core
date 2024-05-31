"""Load an asset in Blender from an Alembic file."""

from pathlib import Path
from pprint import pformat
from typing import Dict, List, Optional

import bpy

from ayon_core.pipeline import (
    get_representation_path,
    AVALON_CONTAINER_ID,
)
from ayon_blender.api import plugin, lib
from ayon_blender.api.pipeline import (
    AVALON_CONTAINERS,
    AVALON_PROPERTY,
)


class AbcCameraLoader(plugin.BlenderLoader):
    """Load a camera from Alembic file.

    Stores the imported asset in an empty named after the asset.
    """

    product_types = {"camera"}
    representations = {"abc"}

    label = "Load Camera (ABC)"
    icon = "code-fork"
    color = "orange"

    def _remove(self, asset_group):
        objects = list(asset_group.children)

        for obj in objects:
            if obj.type == "CAMERA":
                bpy.data.cameras.remove(obj.data)
            elif obj.type == "EMPTY":
                objects.extend(obj.children)
                bpy.data.objects.remove(obj)

    def _process(self, libpath, asset_group, group_name):
        plugin.deselect_all()

        # Force the creation of the transform cache even if the camera
        # doesn't have an animation. We use the cache to update the camera.
        bpy.ops.wm.alembic_import(
            filepath=libpath, always_add_cache_reader=True)

        objects = lib.get_selection()

        for obj in objects:
            obj.parent = asset_group

        for obj in objects:
            name = obj.name
            obj.name = f"{group_name}:{name}"
            if obj.type != "EMPTY":
                name_data = obj.data.name
                obj.data.name = f"{group_name}:{name_data}"

            if not obj.get(AVALON_PROPERTY):
                obj[AVALON_PROPERTY] = dict()

            avalon_info = obj[AVALON_PROPERTY]
            avalon_info.update({"container_name": group_name})

        plugin.deselect_all()

        return objects

    def process_asset(
        self,
        context: dict,
        name: str,
        namespace: Optional[str] = None,
        options: Optional[Dict] = None,
    ) -> Optional[List]:
        """
        Arguments:
            name: Use pre-defined name
            namespace: Use pre-defined namespace
            context: Full parenthood of representation to load
            options: Additional settings dictionary
        """

        libpath = self.filepath_from_context(context)

        folder_name = context["folder"]["name"]
        product_name = context["product"]["name"]

        asset_name = plugin.prepare_scene_name(folder_name, product_name)
        unique_number = plugin.get_unique_number(folder_name, product_name)
        group_name = plugin.prepare_scene_name(
            folder_name, product_name, unique_number
        )
        namespace = namespace or f"{folder_name}_{unique_number}"

        avalon_container = bpy.data.collections.get(AVALON_CONTAINERS)
        if not avalon_container:
            avalon_container = bpy.data.collections.new(name=AVALON_CONTAINERS)
            bpy.context.scene.collection.children.link(avalon_container)

        asset_group = bpy.data.objects.new(group_name, object_data=None)
        avalon_container.objects.link(asset_group)

        self._process(libpath, asset_group, group_name)

        objects = []
        nodes = list(asset_group.children)

        for obj in nodes:
            objects.append(obj)
            nodes.extend(list(obj.children))

        bpy.context.scene.collection.objects.link(asset_group)

        asset_group[AVALON_PROPERTY] = {
            "schema": "openpype:container-2.0",
            "id": AVALON_CONTAINER_ID,
            "name": name,
            "namespace": namespace or "",
            "loader": str(self.__class__.__name__),
            "representation": context["representation"]["id"],
            "libpath": libpath,
            "asset_name": asset_name,
            "parent": context["representation"]["versionId"],
            "productType": context["product"]["productType"],
            "objectName": group_name,
        }

        self[:] = objects
        return objects

    def exec_update(self, container: Dict, context: Dict):
        """Update the loaded asset.

        This will remove all objects of the current collection, load the new
        ones and add them to the collection.
        If the objects of the collection are used in another collection they
        will not be removed, only unlinked. Normally this should not be the
        case though.

        Warning:
            No nested collections are supported at the moment!
        """
        repre_entity = context["representation"]
        object_name = container["objectName"]
        asset_group = bpy.data.objects.get(object_name)
        libpath = Path(get_representation_path(repre_entity))
        extension = libpath.suffix.lower()

        self.log.info(
            "Container: %s\nRepresentation: %s",
            pformat(container, indent=2),
            pformat(repre_entity, indent=2),
        )

        assert asset_group, (
            f"The asset is not loaded: {container['objectName']}")
        assert libpath, (
            f"No existing library file found for {container['objectName']}")
        assert libpath.is_file(), f"The file doesn't exist: {libpath}"
        assert extension in plugin.VALID_EXTENSIONS, (
            f"Unsupported file: {libpath}")

        metadata = asset_group.get(AVALON_PROPERTY)
        group_libpath = metadata["libpath"]

        normalized_group_libpath = str(
            Path(bpy.path.abspath(group_libpath)).resolve())
        normalized_libpath = str(
            Path(bpy.path.abspath(str(libpath))).resolve())
        self.log.debug(
            "normalized_group_libpath:\n  %s\nnormalized_libpath:\n  %s",
            normalized_group_libpath,
            normalized_libpath,
        )
        if normalized_group_libpath == normalized_libpath:
            self.log.info("Library already loaded, not updating...")
            return

        for obj in asset_group.children:
            found = False
            for constraint in obj.constraints:
                if constraint.type == "TRANSFORM_CACHE":
                    constraint.cache_file.filepath = libpath.as_posix()
                    found = True
                    break
            if not found:
                # This is to keep compatibility with cameras loaded with
                # the old loader
                # Create a new constraint for the cache file
                constraint = obj.constraints.new("TRANSFORM_CACHE")
                bpy.ops.cachefile.open(filepath=libpath.as_posix())
                constraint.cache_file = bpy.data.cache_files[-1]
                constraint.cache_file.scale = 1.0

                # This is a workaround to set the object path. Blender doesn't
                # load the list of object paths until the object is evaluated.
                # This is a hack to force the object to be evaluated.
                # The modifier doesn't need to be removed because camera
                # objects don't have modifiers.
                obj.modifiers.new(
                    name='MeshSequenceCache', type='MESH_SEQUENCE_CACHE')
                bpy.context.evaluated_depsgraph_get()

                constraint.object_path = (
                    constraint.cache_file.object_paths[0].path)

        metadata["libpath"] = str(libpath)
        metadata["representation"] = repre_entity["id"]

    def exec_remove(self, container: Dict) -> bool:
        """Remove an existing container from a Blender scene.

        Arguments:
            container (openpype:container-1.0): Container to remove,
                from `host.ls()`.

        Returns:
            bool: Whether the container was deleted.

        Warning:
            No nested collections are supported at the moment!
        """
        object_name = container["objectName"]
        asset_group = bpy.data.objects.get(object_name)

        if not asset_group:
            return False

        self._remove(asset_group)

        bpy.data.objects.remove(asset_group)

        return True
