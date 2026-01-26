"""
Requires:
    context  -> projectName
    context  -> projectEntity
    instance -> folderPath
    instance -> task

Provides:
    instance -> projectEntity
    instance -> folderEntity
    instance -> taskEntity
"""
import collections

import pyblish.api
import ayon_api


class CollectInstanceEntities(pyblish.api.ContextPlugin):
    """Collect instance entities based on their context.

    Plugin is running for all instances on context even not active instances.

    Logic was separated from CollectInstanceAnatomy data to run the logic
        earlier. Instances that don't have set 'folderPath' will be skipped.
        If there is a plugin adding or changing entities after this plugin
        they should make sure that correct entities are filled. Collect
        anatomy instance data plugin can do that but it runs later.
    """

    order = pyblish.api.CollectorOrder - 0.4
    label = "Collect Instance entities"

    def process(self, context):
        self.log.debug("Collecting entities all instances.")
        self.fill_project_entity(context)
        self.fill_folder_entities(context)
        self.fill_task_entities(context)

    def fill_project_entity(self, context):
        project_entity = context.data.get("projectEntity")
        if not project_entity:
            project_name = context.data["projectName"]
            project_entity = ayon_api.get_project(project_name)
            context.data["projectEntity"] = project_entity

        for instance in context:
            instance.data["projectEntity"] = project_entity

    def fill_folder_entities(self, context):
        self.log.debug("Querying folder entities for instances.")

        project_name = context.data["projectName"]
        context_folder_entity = context.data.get("folderEntity")
        context_folder_path = None
        if context_folder_entity:
            context_folder_path = context_folder_entity["path"]

        instances_missing_folder = collections.defaultdict(list)
        for instance in context:
            instance_folder_entity = instance.data.get("folderEntity")
            instance_folder_path = instance.data.get("folderPath")

            # There is possibility that folderEntity on instance is set
            if instance_folder_entity:
                instance_folder_path = instance_folder_entity["path"]
                if instance_folder_path == instance_folder_path:
                    continue

            if not instance_folder_path:
                continue

            # Check if folder path is the same as what is in context
            # - they may be different, e.g. during editorial publishing
            if (
                context_folder_path
                and context_folder_path == instance_folder_path
            ):
                instance.data["folderEntity"] = context_folder_entity

            else:
                instances_missing_folder[instance_folder_path].append(
                    instance
                )

        if not instances_missing_folder:
            self.log.debug("All instances already had right folder entity.")
            return

        folder_paths = set(instances_missing_folder.keys())
        joined_folder_paths = ", ".join(
            [f"\"{path}\"" for path in folder_paths]
        )
        self.log.debug(
            f"Fetching folder entities with paths: {joined_folder_paths}"
        )

        folder_entities_by_path = {
            folder_entity["path"]: folder_entity
            for folder_entity in ayon_api.get_folders(
                project_name, folder_paths=folder_paths
            )
        }

        not_found_folder_paths = set()
        for folder_path, instances in instances_missing_folder.items():
            folder_entity = folder_entities_by_path.get(folder_path)
            if not folder_entity:
                not_found_folder_paths.add(folder_path)
                continue

            for instance in instances:
                instance.data["folderEntity"] = folder_entity

        if not_found_folder_paths:
            joined_folder_paths = ", ".join(
                [f"\"{path}\"" for path in not_found_folder_paths]
            )
            self.log.warning(
                f"Not found folder entities with paths {joined_folder_paths}."
            )

    def fill_task_entities(self, context):
        self.log.debug("Querying task entities for instances.")
        project_name = context.data["projectName"]

        context_folder_entity = context.data.get("folderEntity")
        context_folder_id = None
        if context_folder_entity:
            context_folder_id = context_folder_entity["id"]
        context_task_entity = context.data.get("taskEntity")
        context_task_name = None
        if context_task_entity:
            context_task_name = context_task_entity["name"]

        instances_missing_task = {}
        folder_path_by_id = {}
        for instance in context:
            folder_entity = instance.data.get("folderEntity")
            # Skip if instance does not have filled folder entity
            if not folder_entity:
                continue
            folder_id = folder_entity["id"]
            folder_path_by_id[folder_id] = folder_entity["path"]

            task_entity = instance.data.get("taskEntity")
            _task_name = instance.data.get("task")

            # There is possibility that taskEntity on instance is set
            if task_entity:
                task_parent_id = task_entity["folderId"]
                instance_task_name = task_entity["name"]
                if (
                    folder_id == task_parent_id
                    and instance_task_name == _task_name
                ):
                    continue

            # Check if folder path is the same as what is in context
            # - they may be different, e.g. in NukeStudio
            if (
                context_folder_id == folder_id
                and context_task_name == _task_name
            ):
                instance.data["taskEntity"] = context_task_entity
                continue

            _by_folder_id = instances_missing_task.setdefault(folder_id, {})
            _by_task_name = _by_folder_id.setdefault(_task_name, [])
            _by_task_name.append(instance)

        if not instances_missing_task:
            self.log.debug("All instances already had right task entity.")
            return

        self.log.debug("Querying task entities")

        all_folder_ids = set(instances_missing_task.keys())
        all_task_names = set()
        for per_task in instances_missing_task.values():
            all_task_names |= set(per_task.keys())
        all_task_names.discard(None)

        task_entities = []
        if all_task_names:
            task_entities = ayon_api.get_tasks(
                project_name,
                folder_ids=all_folder_ids,
                task_names=all_task_names
            )
        task_entity_by_ids = {}
        for task_entity in task_entities:
            folder_id = task_entity["folderId"]
            task_name = task_entity["name"]
            _by_folder_id = task_entity_by_ids.setdefault(folder_id, {})
            _by_folder_id[task_name] = task_entity

        not_found_task_paths = []
        for folder_id, by_task in instances_missing_task.items():
            for task_name, instances in by_task.items():
                task_entity = (
                    task_entity_by_ids
                    .get(folder_id, {})
                    .get(task_name)
                )
                if task_name and not task_entity:
                    folder_path = folder_path_by_id[folder_id]
                    not_found_task_paths.append(
                        "/".join([folder_path, task_name])
                    )

                for instance in instances:
                    instance.data["taskEntity"] = task_entity

        if not_found_task_paths:
            joined_paths = ", ".join(
                [f'"{path}"' for path in not_found_task_paths]
            )
            self.log.warning(
                f"Not found task entities with paths {joined_paths}."
            )
