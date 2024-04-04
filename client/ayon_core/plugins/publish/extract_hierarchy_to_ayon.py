import collections
import copy
import json
import uuid
import pyblish.api

from ayon_api import slugify_string, get_folders, get_tasks
from ayon_api.entity_hub import EntityHub

from ayon_core.pipeline.template_data import (
    get_folder_template_data,
    get_task_template_data,
)


def _default_json_parse(value):
    return str(value)


class ExtractHierarchyToAYON(pyblish.api.ContextPlugin):
    """Create entities in AYON based on collected data."""

    order = pyblish.api.ExtractorOrder - 0.01
    label = "Extract Hierarchy To AYON"
    families = ["clip", "shot"]

    def process(self, context):
        if not context.data.get("hierarchyContext"):
            self.log.debug("Skipping ExtractHierarchyToAYON")
            return

        project_name = context.data["projectName"]
        self._create_hierarchy(context, project_name)
        self._fill_instance_entities(context, project_name)

    def _fill_instance_entities(self, context, project_name):
        instances_by_folder_path = collections.defaultdict(list)
        for instance in context:
            if instance.data.get("publish") is False:
                continue

            instance_entity = instance.data.get("folderEntity")
            if instance_entity:
                continue

            folder_path = instance.data.get("folderPath")
            instances_by_folder_path[folder_path].append(instance)

        project_entity = context.data["projectEntity"]
        folder_entities = get_folders(
            project_name, folder_paths=instances_by_folder_path.keys()
        )
        folder_entities_by_path = {
            folder_entity["path"]: folder_entity
            for folder_entity in folder_entities
        }
        all_task_names = set()
        folder_ids = set()
        # Fill folderEntity and prepare data for task entities
        for folder_path, instances in instances_by_folder_path.items():
            folder_entity = folder_entities_by_path[folder_path]
            folder_ids.add(folder_entity["id"])
            for instance in instances:
                task_name = instance.data.get("task")
                all_task_names.add(task_name)

        # Query task entities
        # Discard 'None' task names
        all_task_names.discard(None)
        tasks_by_name_by_folder_id = {
            folder_id: {} for folder_id in folder_ids
        }
        task_entities = []
        if all_task_names:
            task_entities = get_tasks(
                project_name,
                task_names=all_task_names,
                folder_ids=folder_ids,
            )
        for task_entity in task_entities:
            task_name = task_entity["name"]
            folder_id = task_entity["folderId"]
            tasks_by_name_by_folder_id[folder_id][task_name] = task_entity

        for folder_path, instances in instances_by_folder_path.items():
            folder_entity = folder_entities_by_path[folder_path]
            folder_id = folder_entity["id"]
            folder_data = get_folder_template_data(
                folder_entity, project_name
            )
            task_entities_by_name = tasks_by_name_by_folder_id[folder_id]
            for instance in instances:
                task_name = instance.data.get("task")
                task_entity = task_entities_by_name.get(task_name)
                template_data = {}
                if task_entity:
                    template_data = get_task_template_data(
                        project_entity, task_entity
                    )
                template_data.update(copy.deepcopy(folder_data))

                instance.data["anatomyData"].update(template_data)
                instance.data["folderEntity"] = folder_entity
                instance.data["taskEntity"] = task_entity

    def _create_hierarchy(self, context, project_name):
        hierarchy_context = self._filter_hierarchy(context)
        if not hierarchy_context:
            self.log.debug("All folders were filtered out")
            return

        self.log.debug("Hierarchy_context: {}".format(
            json.dumps(hierarchy_context, default=_default_json_parse)
        ))

        entity_hub = EntityHub(project_name)
        project = entity_hub.project_entity
        folder_type_name_by_low_name = {
            folder_type_item["name"].lower(): folder_type_item["name"]
            for folder_type_item in project.get_folder_types()
        }

        hierarchy_match_queue = collections.deque()
        hierarchy_match_queue.append((project, hierarchy_context))
        while hierarchy_match_queue:
            item = hierarchy_match_queue.popleft()
            entity, entity_info = item

            # Update attributes of entities
            for attr_name, attr_value in entity_info["attributes"].items():
                if attr_name in entity.attribs:
                    entity.attribs[attr_name] = attr_value

            # Check if info has any children to sync
            children_info = entity_info["children"]
            tasks_info = entity_info["tasks"]
            if not tasks_info and not children_info:
                continue

            # Prepare children by lowered name to easily find matching entities
            children_by_low_name = {
                child.name.lower(): child
                for child in entity.children
            }

            # Create tasks if are not available
            for task_info in tasks_info:
                task_label = task_info["name"]
                task_name = slugify_string(task_label)
                if task_name == task_label:
                    task_label = None
                task_entity = children_by_low_name.get(task_name.lower())
                # TODO propagate updates of tasks if there are any
                # TODO check if existing entity have 'task' type
                if task_entity is None:
                    task_entity = entity_hub.add_new_task(
                        task_info["type"],
                        parent_id=entity.id,
                        name=task_name
                    )

                if task_label:
                    task_entity.label = task_label

            # Create/Update sub-folders
            for child_info in children_info:
                child_label = child_info["name"]
                child_name = slugify_string(child_label)
                if child_name == child_label:
                    child_label = None
                # TODO check if existing entity have 'folder' type
                child_entity = children_by_low_name.get(child_name.lower())
                if child_entity is None:
                    folder_type = folder_type_name_by_low_name.get(
                        child_info["folder_type"].lower()
                    )
                    if folder_type is None:
                        # TODO add validator for folder type validations
                        self.log.warning((
                            "Couldn't find folder type '{}'"
                        ).format(child_info["folder_type"]))
                        folder_type = "Folder"

                    child_entity = entity_hub.add_new_folder(
                        folder_type,
                        parent_id=entity.id,
                        name=child_name
                    )

                if child_label:
                    child_entity.label = child_label

                # Add folder to queue
                hierarchy_match_queue.append((child_entity, child_info))

        entity_hub.commit_changes()

    def _filter_hierarchy(self, context):
        """Filter hierarchy context by active folder names.

        Hierarchy context is filtered to folder names on active instances.

        Change hierarchy context to unified structure which suits logic in
        entity creation.

        Output example:
            {
                "name": "MyProject",
                "entity_type": "project",
                "attributes": {},
                "tasks": [],
                "children": [
                    {
                        "name": "seq_01",
                        "entity_type": "Sequence",
                        "attributes": {},
                        "tasks": [],
                        "children": [
                            ...
                        ]
                    },
                    ...
                ]
            }

        Todos:
            Change how active folder are defined (names won't be enough in
                AYON).

        Args:
            context (pyblish.api.Context): Pyblish context.

        Returns:
            dict[str, Any]: Hierarchy structure filtered by folder names.
        """

        # filter only the active publishing instances
        active_folder_paths = set()
        for instance in context:
            if instance.data.get("publish", True) is not False:
                active_folder_paths.add(instance.data.get("folderPath"))

        active_folder_paths.discard(None)

        if not active_folder_paths:
            return None

        project_item = None
        project_children_context = None
        hierarchy_context = copy.deepcopy(context.data["hierarchyContext"])
        for key, value in hierarchy_context.items():
            project_item = copy.deepcopy(value)
            project_children_context = project_item.pop("children", None)
            project_item["name"] = key
            project_item["tasks"] = []
            project_item["attributes"] = project_item.pop(
                "attributes", {}
            )
            project_item["children"] = []

        if not project_children_context:
            return None

        project_id = uuid.uuid4().hex
        items_by_id = {project_id: project_item}
        parent_id_by_item_id = {project_id: None}
        valid_ids = set()

        hierarchy_queue = collections.deque()
        hierarchy_queue.append((project_id, "", project_children_context))
        while hierarchy_queue:
            queue_item = hierarchy_queue.popleft()
            parent_id, parent_path, children_context = queue_item
            if not children_context:
                continue

            for folder_name, folder_info in children_context.items():
                folder_path = "{}/{}".format(parent_path, folder_name)
                if (
                    folder_path not in active_folder_paths
                    and not folder_info.get("children")
                ):
                    continue

                item_id = uuid.uuid4().hex
                new_item = copy.deepcopy(folder_info)
                new_children_context = new_item.pop("children", None)
                tasks = new_item.pop("tasks", {})

                new_item["name"] = folder_name
                new_item["children"] = []
                task_items = []
                for task_name, task_info in tasks.items():
                    task_info["name"] = task_name
                    task_items.append(task_info)
                new_item["tasks"] = task_items
                new_item["attributes"] = new_item.pop("attributes", {})

                items_by_id[item_id] = new_item
                parent_id_by_item_id[item_id] = parent_id

                if folder_path in active_folder_paths:
                    valid_ids.add(item_id)
                hierarchy_queue.append(
                    (item_id, folder_path, new_children_context)
                )

        if not valid_ids:
            return None

        for item_id in set(valid_ids):
            parent_id = parent_id_by_item_id[item_id]
            while parent_id is not None and parent_id not in valid_ids:
                valid_ids.add(parent_id)
                parent_id = parent_id_by_item_id[parent_id]

        valid_ids.discard(project_id)
        for item_id in valid_ids:
            parent_id = parent_id_by_item_id[item_id]
            item = items_by_id[item_id]
            parent_item = items_by_id[parent_id]
            parent_item["children"].append(item)

        if not project_item["children"]:
            return None
        return project_item
