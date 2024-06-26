import inspect

import ayon_maya.api.action
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    RepairAction,
    ValidateMeshOrder,
)
from ayon_maya.api import plugin
from maya import cmds


class ValidateMeshUVSetMap1(plugin.MayaInstancePlugin,
                            OptionalPyblishPluginMixin):
    """Validate model's default set exists and is named 'map1'.

    In Maya meshes by default have a uv set named "map1" that cannot be
    deleted. It can be renamed however, introducing some issues with some
    renderers. As such we ensure the first (default) UV set index is named
    "map1".

    """

    order = ValidateMeshOrder
    families = ['model']
    optional = True
    label = "Mesh has map1 UV Set"
    actions = [ayon_maya.api.action.SelectInvalidAction,
               RepairAction]

    @classmethod
    def get_invalid(cls, instance):

        meshes = cmds.ls(instance, type='mesh', long=True)

        invalid = []
        for mesh in meshes:

            # Get existing mapping of uv sets by index
            indices = cmds.polyUVSet(mesh, query=True, allUVSetsIndices=True)
            maps = cmds.polyUVSet(mesh, query=True, allUVSets=True)
            if not indices or not maps:
                cls.log.warning("Mesh has no UV set: %s", mesh)
                invalid.append(mesh)
                continue

            mapping = dict(zip(indices, maps))

            # Get the uv set at index zero.
            name = mapping[0]
            if name != "map1":
                invalid.append(mesh)

        return invalid

    def process(self, instance):
        """Process all the nodes in the instance 'objectSet'"""
        if not self.is_active(instance.data):
            return

        invalid = self.get_invalid(instance)
        if invalid:

            invalid_list = "\n".join(f"- {node}" for node in invalid)

            raise PublishValidationError(
                "Meshes found without 'map1' UV set:\n"
                "{0}".format(invalid_list),
                description=self.get_description()
            )

    @classmethod
    def repair(cls, instance):
        """Rename uv map at index zero to map1"""

        for mesh in cls.get_invalid(instance):

            # Get existing mapping of uv sets by index
            indices = cmds.polyUVSet(mesh, query=True, allUVSetsIndices=True)
            maps = cmds.polyUVSet(mesh, query=True, allUVSets=True)
            if not indices or not maps:
                # No UV set exist at all, create a `map1` uv set
                # This may fail silently if the mesh has no geometry at all
                cmds.polyUVSet(mesh, create=True, uvSet="map1")
                continue

            mapping = dict(zip(indices, maps))

            # Ensure there is no uv set named map1 to avoid
            # a clash on renaming the "default uv set" to map1
            existing = set(maps)
            if "map1" in existing:

                # Find a unique name index
                i = 2
                while True:
                    name = "map{0}".format(i)
                    if name not in existing:
                        break
                    i += 1

                cls.log.warning("Renaming clashing uv set name on mesh"
                                " %s to '%s'", mesh, name)

                cmds.polyUVSet(mesh,
                               rename=True,
                               uvSet="map1",
                               newUVSet=name)

            # Rename the initial index to map1
            original = mapping[0]
            cmds.polyUVSet(mesh,
                           rename=True,
                           uvSet=original,
                           newUVSet="map1")

    @staticmethod
    def get_description():
        return inspect.cleandoc("""### Mesh found without map1 uv set

        A mesh must have a default UV set named `map1` to adhere to the default
        mesh behavior of Maya meshes.

        There may be meshes that:
        - Have no UV set
        - Have no `map1` uv set but are using a different name
        - Have a `map1` uv set, but it's not the default (first index)


        #### Repair

        Using repair will try to make the first UV set the `map1` uv set. If it
        does not exist yet it will be created or renames the current first
        UV set to `map1`.
        """)
