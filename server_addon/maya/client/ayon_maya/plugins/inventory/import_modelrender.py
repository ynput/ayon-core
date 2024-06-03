import re
import json

import ayon_api

from ayon_core.pipeline.load import get_representation_contexts_by_ids
from ayon_core.pipeline import (
    InventoryAction,
    get_current_project_name,
)
from ayon_maya.api.lib import (
    maintained_selection,
    apply_shaders
)


class ImportModelRender(InventoryAction):

    label = "Import Model Render Sets"
    icon = "industry"
    color = "#55DDAA"

    scene_type_regex = "meta.render.m[ab]"
    look_data_type = "meta.render.json"

    @staticmethod
    def is_compatible(container):
        return (
            container.get("loader") == "ReferenceLoader"
            and container.get("name", "").startswith("model")
        )

    def process(self, containers):
        from maya import cmds  # noqa: F401

        # --- Query entities that will be used ---
        project_name = get_current_project_name()
        # Collect representation ids from all containers
        repre_ids = {
            container["representation"]
            for container in containers
        }
        # Create mapping of representation id to version id
        # - used in containers loop
        version_id_by_repre_id = {
            repre_entity["id"]: repre_entity["versionId"]
            for repre_entity in ayon_api.get_representations(
                project_name,
                representation_ids=repre_ids,
                fields={"id", "versionId"}
            )
        }

        # Find all representations of the versions
        version_ids = set(version_id_by_repre_id.values())
        repre_entities = ayon_api.get_representations(
            project_name,
            version_ids=version_ids,
            fields={"id", "name", "versionId"}
        )
        repre_entities_by_version_id = {
            version_id: []
            for version_id in version_ids
        }
        for repre_entity in repre_entities:
            version_id = repre_entity["versionId"]
            repre_entities_by_version_id[version_id].append(repre_entity)

        look_repres_by_version_id = {}
        look_repre_ids = set()
        for version_id, repre_entities in (
            repre_entities_by_version_id.items()
        ):
            json_repre = None
            look_repres = []
            scene_type_regex = re.compile(self.scene_type_regex)
            for repre_entity in repre_entities:
                repre_name = repre_entity["name"]
                if repre_name == self.look_data_type:
                    json_repre = repre_entity

                elif scene_type_regex.fullmatch(repre_name):
                    look_repres.append(repre_entity)

            look_repre = look_repres[0] if look_repres else None
            if look_repre:
                look_repre_ids.add(look_repre["id"])
            if json_repre:
                look_repre_ids.add(json_repre["id"])

            look_repres_by_version_id[version_id] = (json_repre, look_repre)

        contexts_by_repre_id = get_representation_contexts_by_ids(
            project_name, look_repre_ids
        )

        # --- Real process logic ---
        # Loop over containers and assign the looks
        for container in containers:
            con_name = container["objectName"]
            nodes = []
            for n in cmds.sets(con_name, query=True, nodesOnly=True) or []:
                if cmds.nodeType(n) == "reference":
                    nodes += cmds.referenceQuery(n, nodes=True)
                else:
                    nodes.append(n)

            repre_id = container["representation"]
            version_id = version_id_by_repre_id.get(repre_id)
            if version_id is None:
                print("Representation '{}' was not found".format(repre_id))
                continue

            json_repre, look_repre = look_repres_by_version_id[version_id]

            print("Importing render sets for model %r" % con_name)
            self._assign_model_render(
                nodes, json_repre, look_repre, contexts_by_repre_id
            )

    def _assign_model_render(
        self, nodes, json_repre, look_repre, contexts_by_repre_id
    ):
        """Assign nodes a specific published model render data version by id.

        This assumes the nodes correspond with the asset.

        Args:
            nodes (list): nodes to assign render data to
            json_repre (dict[str, Any]): Representation entity of the json
                file.
            look_repre (dict[str, Any]): First representation entity of the
                look files.
            contexts_by_repre_id (dict[str, Any]): Mapping of representation
                id to its context.

        Returns:
            None
        """

        from maya import cmds  # noqa: F401

        # QUESTION shouldn't be json representation validated too?
        if not look_repre:
            print("No model render sets for this model version..")
            return

        # TODO use 'get_representation_path_with_anatomy' instead
        #   of 'filepath_from_context'
        context = contexts_by_repre_id.get(look_repre["id"])
        maya_file = self.filepath_from_context(context)

        context = contexts_by_repre_id.get(json_repre["id"])
        json_file = self.filepath_from_context(context)

        # Import the look file
        with maintained_selection():
            shader_nodes = cmds.file(maya_file,
                                     i=True,  # import
                                     returnNewNodes=True)
            # imprint context data

        # Load relationships
        shader_relation = json_file
        with open(shader_relation, "r") as f:
            relationships = json.load(f)

        # Assign relationships
        apply_shaders(relationships, shader_nodes, nodes)
