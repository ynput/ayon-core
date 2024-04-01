from typing import Dict, List, Optional
from pathlib import Path

import bpy

from ayon_core.pipeline import (
    get_representation_path,
    AVALON_CONTAINER_ID,
    registered_host
)
from ayon_core.pipeline.create import CreateContext
from ayon_core.hosts.blender.api import plugin
from ayon_core.hosts.blender.api.lib import imprint
from ayon_core.hosts.blender.api.pipeline import (
    AVALON_CONTAINERS,
    AVALON_PROPERTY,
)


class BlendLoader(plugin.AssetLoader):
    """Load assets from a .blend file."""

    product_types = {"model", "rig", "layout", "camera"}
    representations = ["blend"]

    label = "Append Blend"
    icon = "code-fork"
    color = "orange"

    @staticmethod
    def _get_asset_container(objects):
        empties = [obj for obj in objects if obj.type == 'EMPTY']

        for empty in empties:
            if empty.get(AVALON_PROPERTY) and empty.parent is None:
                return empty

        return None

    @staticmethod
    def get_all_container_parents(asset_group):
        parent_containers = []
        parent = asset_group.parent
        while parent:
            if parent.get(AVALON_PROPERTY):
                parent_containers.append(parent)
            parent = parent.parent

        return parent_containers

    def _post_process_layout(self, container, asset, representation):
        rigs = [
            obj for obj in container.children_recursive
            if (
                obj.type == 'EMPTY' and
                obj.get(AVALON_PROPERTY) and
                obj.get(AVALON_PROPERTY).get('family') == 'rig'
            )
        ]
        if not rigs:
            return

        # Create animation instances for each rig
        creator_identifier = "io.openpype.creators.blender.animation"
        host = registered_host()
        create_context = CreateContext(host)

        for rig in rigs:
            create_context.create(
                creator_identifier=creator_identifier,
                variant=rig.name.split(':')[-1],
                pre_create_data={
                    "use_selection": False,
                    "asset_group": rig
                }
            )

    def _process_data(self, libpath, group_name):
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

        container = self._get_asset_container(data_to.objects)
        assert container, "No asset group found"

        container.name = group_name
        container.empty_display_type = 'SINGLE_ARROW'

        # Link the collection to the scene
        bpy.context.scene.collection.objects.link(container)

        # Link all the container children to the collection
        for obj in container.children_recursive:
            bpy.context.scene.collection.objects.link(obj)

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

        representation = context["representation"]["id"]

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

        container, members = self._process_data(libpath, group_name)

        if product_type == "layout":
            self._post_process_layout(container, folder_name, representation)

        avalon_container.objects.link(container)

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
        asset_group = bpy.data.objects.get(group_name)
        libpath = Path(get_representation_path(repre_entity)).as_posix()

        assert asset_group, (
            f"The asset is not loaded: {container['objectName']}"
        )

        transform = asset_group.matrix_basis.copy()
        old_data = dict(asset_group.get(AVALON_PROPERTY))
        old_members = old_data.get("members", [])
        parent = asset_group.parent

        actions = {}
        objects_with_anim = [
            obj for obj in asset_group.children_recursive
            if obj.animation_data]
        for obj in objects_with_anim:
            # Check if the object has an action and, if so, add it to a dict
            # so we can restore it later. Save and restore the action only
            # if it wasn't originally loaded from the current asset.
            if obj.animation_data.action not in old_members:
                actions[obj.name] = obj.animation_data.action

        self.exec_remove(container)

        asset_group, members = self._process_data(libpath, group_name)

        avalon_container = bpy.data.collections.get(AVALON_CONTAINERS)
        avalon_container.objects.link(asset_group)

        asset_group.matrix_basis = transform
        asset_group.parent = parent

        # Restore the actions
        for obj in asset_group.children_recursive:
            if obj.name in actions:
                if not obj.animation_data:
                    obj.animation_data_create()
                obj.animation_data.action = actions[obj.name]

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

        # We need to update all the parent container members
        parent_containers = self.get_all_container_parents(asset_group)

        for parent_container in parent_containers:
            parent_members = parent_container[AVALON_PROPERTY]["members"]
            parent_container[AVALON_PROPERTY]["members"] = (
                parent_members + members)

    def exec_remove(self, container: Dict) -> bool:
        """
        Remove an existing container from a Blender scene.
        """
        group_name = container["objectName"]
        asset_group = bpy.data.objects.get(group_name)

        attrs = [
            attr for attr in dir(bpy.data)
            if isinstance(
                getattr(bpy.data, attr),
                bpy.types.bpy_prop_collection
            )
        ]

        members = asset_group.get(AVALON_PROPERTY).get("members", [])

        # We need to update all the parent container members
        parent_containers = self.get_all_container_parents(asset_group)

        for parent in parent_containers:
            parent.get(AVALON_PROPERTY)["members"] = list(filter(
                lambda i: i not in members,
                parent.get(AVALON_PROPERTY).get("members", [])))

        for attr in attrs:
            for data in getattr(bpy.data, attr):
                if data in members:
                    # Skip the asset group
                    if data == asset_group:
                        continue
                    getattr(bpy.data, attr).remove(data)

        bpy.data.objects.remove(asset_group)
