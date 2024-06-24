from ayon_core.pipeline import (
    InventoryAction,
    get_current_project_name,
)
from ayon_core.pipeline.load import get_representation_contexts_by_ids
from ayon_maya.api.lib import (
    create_rig_animation_instance,
    get_container_members,
)


class RecreateRigAnimationInstance(InventoryAction):
    """Recreate animation publish instance for loaded rigs"""

    label = "Recreate rig animation instance"
    icon = "wrench"
    color = "#888888"

    @staticmethod
    def is_compatible(container):
        return (
            container.get("loader") == "ReferenceLoader"
            and container.get("name", "").startswith("rig")
        )

    def process(self, containers):
        project_name = get_current_project_name()
        repre_ids = {
            container["representation"]
            for container in containers
        }
        contexts_by_repre_id = get_representation_contexts_by_ids(
            project_name, repre_ids
        )

        for container in containers:
            # todo: delete an existing entry if it exist or skip creation

            namespace = container["namespace"]
            repre_id = container["representation"]
            context = contexts_by_repre_id[repre_id]
            nodes = get_container_members(container)

            create_rig_animation_instance(nodes, context, namespace)
