from typing import Dict, List, Optional
from pathlib import Path

import bpy

from ayon_core.pipeline import (
    get_representation_path,
    AVALON_CONTAINER_ID,
)
from ayon_blender.api import plugin
from ayon_blender.api.lib import imprint
from ayon_blender.api.pipeline import (
    AVALON_CONTAINERS,
    AVALON_PROPERTY,
)


class BlendSceneLoader(plugin.BlenderLoader):
    """Load assets from a .blend file."""

    product_types = {"blendScene"}
    representations = {"blend"}

    label = "Append Blend"
    icon = "code-fork"
    color = "orange"

    @staticmethod
    def _get_asset_container(collections):
        for coll in collections:
            parents = [c for c in collections if c.user_of_id(coll)]
            if coll.get(AVALON_PROPERTY) and not parents:
                return coll

        return None

    def _process_data(self, libpath, group_name, product_type):
        # Append all the data from the .blend file
        with bpy.data.libraries.load(
            libpath, link=False, relative=False
        ) as (data_from, data_to):
            for attr in dir(data_to):
                setattr(data_to, attr, getattr(data_from, attr))

        members = []

        # Rename the object to add the asset name
        for attr in dir(data_to):
            for data in getattr(data_to, attr):
                data.name = f"{group_name}:{data.name}"
                members.append(data)

        container = self._get_asset_container(
            data_to.collections)
        assert container, "No asset group found"

        container.name = group_name

        # Link the group to the scene
        bpy.context.scene.collection.children.link(container)

        # Remove the library from the blend file
        filepath = bpy.path.basename(libpath)
        # Blender has a limit of 63 characters for any data name.
        # If the filepath is longer, it will be truncated.
        if len(filepath) > 63:
            filepath = filepath[:63]
        library = bpy.data.libraries.get(filepath)
        bpy.data.libraries.remove(library)

        return container, members

    def process_asset(
        self, context: dict, name: str, namespace: Optional[str] = None,
        options: Optional[Dict] = None
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

        try:
            product_type = context["product"]["productType"]
        except ValueError:
            product_type = "model"

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

        container, members = self._process_data(
            libpath, group_name, product_type
        )

        avalon_container.children.link(container)

        data = {
            "schema": "openpype:container-2.0",
            "id": AVALON_CONTAINER_ID,
            "name": name,
            "namespace": namespace or '',
            "loader": str(self.__class__.__name__),
            "representation": context["representation"]["id"],
            "libpath": libpath,
            "asset_name": asset_name,
            "parent": context["representation"]["versionId"],
            "productType": context["product"]["productType"],
            "objectName": group_name,
            "members": members,
        }

        container[AVALON_PROPERTY] = data

        objects = [
            obj for obj in bpy.data.objects
            if obj.name.startswith(f"{group_name}:")
        ]

        self[:] = objects
        return objects

    def exec_update(self, container: Dict, context: Dict):
        """
        Update the loaded asset.
        """
        repre_entity = context["representation"]
        group_name = container["objectName"]
        asset_group = bpy.data.collections.get(group_name)
        libpath = Path(get_representation_path(repre_entity)).as_posix()

        assert asset_group, (
            f"The asset is not loaded: {container['objectName']}"
        )

        # Get the parents of the members of the asset group, so we can
        # re-link them after the update.
        # Also gets the transform for each object to reapply after the update.
        collection_parents = {}
        member_transforms = {}
        members = asset_group.get(AVALON_PROPERTY).get("members", [])
        loaded_collections = {c for c in bpy.data.collections if c in members}
        loaded_collections.add(bpy.data.collections.get(AVALON_CONTAINERS))
        for member in members:
            if isinstance(member, bpy.types.Object):
                member_parents = set(member.users_collection)
                member_transforms[member.name] = member.matrix_basis.copy()
            elif isinstance(member, bpy.types.Collection):
                member_parents = {
                    c for c in bpy.data.collections if c.user_of_id(member)}
            else:
                continue

            member_parents = member_parents.difference(loaded_collections)
            if member_parents:
                collection_parents[member.name] = list(member_parents)

        old_data = dict(asset_group.get(AVALON_PROPERTY))

        self.exec_remove(container)

        product_type = container.get("productType")
        if product_type is None:
            product_type = container["family"]
        asset_group, members = self._process_data(
            libpath, group_name, product_type
        )

        for member in members:
            if member.name in collection_parents:
                for parent in collection_parents[member.name]:
                    if isinstance(member, bpy.types.Object):
                        parent.objects.link(member)
                    elif isinstance(member, bpy.types.Collection):
                        parent.children.link(member)
            if member.name in member_transforms and isinstance(
                member, bpy.types.Object
            ):
                member.matrix_basis = member_transforms[member.name]

        avalon_container = bpy.data.collections.get(AVALON_CONTAINERS)
        avalon_container.children.link(asset_group)

        # Restore the old data, but reset members, as they don't exist anymore
        # This avoids a crash, because the memory addresses of those members
        # are not valid anymore
        old_data["members"] = []
        asset_group[AVALON_PROPERTY] = old_data

        new_data = {
            "libpath": libpath,
            "representation": repre_entity["id"],
            "parent": repre_entity["versionId"],
            "members": members,
        }

        imprint(asset_group, new_data)

    def exec_remove(self, container: Dict) -> bool:
        """
        Remove an existing container from a Blender scene.
        """
        group_name = container["objectName"]
        asset_group = bpy.data.collections.get(group_name)

        members = set(asset_group.get(AVALON_PROPERTY).get("members", []))

        if members:
            for attr_name in dir(bpy.data):
                attr = getattr(bpy.data, attr_name)
                if not isinstance(attr, bpy.types.bpy_prop_collection):
                    continue

                # ensure to make a list copy because we
                # we remove members as we iterate
                for data in list(attr):
                    if data not in members or data == asset_group:
                        continue

                    attr.remove(data)

        bpy.data.collections.remove(asset_group)
