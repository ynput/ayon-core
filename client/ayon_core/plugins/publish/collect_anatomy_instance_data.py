"""
Requires:
    context     -> projectName
    context     -> projectEntity
    context     -> anatomyData
    instance    -> folderPath
    instance    -> productName
    instance    -> productType

Optional:
    context     -> folderEntity
    context     -> taskEntity
    instance    -> task
    instance    -> taskEntity
    instance    -> version
    instance    -> resolutionWidth
    instance    -> resolutionHeight
    instance    -> fps

Provides:
    instance    -> projectEntity
    instance    -> folderEntity
    instance    -> taskEntity
    instance    -> anatomyData
    instance    -> version
    instance    -> latestVersion
"""

import copy
import json
import collections

import pyblish.api
import ayon_api

from ayon_core.pipeline.version_start import get_versioning_start


class CollectAnatomyInstanceData(pyblish.api.ContextPlugin):
    """Collect Instance specific Anatomy data.

    Plugin is running for all instances on context even not active instances.
    """

    order = pyblish.api.CollectorOrder + 0.49
    label = "Collect Anatomy Instance data"

    follow_workfile_version = False

    def process(self, context):
        self.log.debug("Collecting anatomy data for all instances.")

        project_name = context.data["projectName"]
        self.fill_missing_folder_entities(context, project_name)
        self.fill_missing_task_entities(context, project_name)
        self.fill_latest_versions(context, project_name)
        self.fill_anatomy_data(context)

        self.log.debug("Anatomy Data collection finished.")

    def fill_missing_folder_entities(self, context, project_name):
        self.log.debug("Querying folder entities for instances.")

        context_folder_entity = context.data.get("folderEntity")
        context_folder_path = None
        if context_folder_entity:
            context_folder_path = context_folder_entity["path"]

        instances_missing_folder = collections.defaultdict(list)
        for instance in context:
            instance_folder_entity = instance.data.get("folderEntity")
            _folder_path = instance.data["folderPath"]

            # There is possibility that folderEntity on instance is set
            if instance_folder_entity:
                instance_folder_path = instance_folder_entity["path"]
                if instance_folder_path == _folder_path:
                    continue

            # Check if folder path is the same as what is in context
            # - they may be different, e.g. during editorial publishing
            if context_folder_path and context_folder_path == _folder_path:
                instance.data["folderEntity"] = context_folder_entity

            else:
                instances_missing_folder[_folder_path].append(
                    instance
                )

        if not instances_missing_folder:
            self.log.debug("All instances already had right folder entity.")
            return

        folder_paths = list(instances_missing_folder.keys())
        self.log.debug("Querying folder entities with paths: {}".format(
            ", ".join(["\"{}\"".format(path) for path in folder_paths])
        ))

        folder_entities_by_path = {
            folder_entity["path"]: folder_entity
            for folder_entity in ayon_api.get_folders(
                project_name, folder_paths=folder_paths
            )
        }

        not_found_folder_paths = []
        for folder_path, instances in instances_missing_folder.items():
            folder_entity = folder_entities_by_path.get(folder_path)
            if not folder_entity:
                not_found_folder_paths.append(folder_path)
                continue

            for _instance in instances:
                _instance.data["folderEntity"] = folder_entity

        if not_found_folder_paths:
            joined_folder_paths = ", ".join(
                ["\"{}\"".format(path) for path in not_found_folder_paths]
            )
            self.log.warning((
                "Not found folder entities with paths \"{}\"."
            ).format(joined_folder_paths))

    def fill_missing_task_entities(self, context, project_name):
        self.log.debug("Querying task entities for instances.")

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
            # Skip if instnace does not have filled folder entity
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
                ["\"{}\"".format(path) for path in not_found_task_paths]
            )
            self.log.warning((
                "Not found task entities with paths \"{}\"."
            ).format(joined_paths))

    def fill_latest_versions(self, context, project_name):
        """Try to find latest version for each instance's product name.

        Key "latestVersion" is always set to latest version or `None`.

        Args:
            context (pyblish.Context)

        Returns:
            None

        """
        self.log.debug("Querying latest versions for instances.")

        hierarchy = {}
        names_by_folder_ids = collections.defaultdict(set)
        for instance in context:
            # Make sure `"latestVersion"` key is set
            latest_version = instance.data.get("latestVersion")
            instance.data["latestVersion"] = latest_version

            # Skip instances without "folderEntity"
            folder_entity = instance.data.get("folderEntity")
            if not folder_entity:
                continue

            # Store folder ids and product names for queries
            folder_id = folder_entity["id"]
            product_name = instance.data["productName"]

            # Prepare instance hierarchy for faster filling latest versions
            if folder_id not in hierarchy:
                hierarchy[folder_id] = {}
            if product_name not in hierarchy[folder_id]:
                hierarchy[folder_id][product_name] = []
            hierarchy[folder_id][product_name].append(instance)
            names_by_folder_ids[folder_id].add(product_name)

        product_entities = []
        if names_by_folder_ids:
            product_entities = list(ayon_api.get_products(
                project_name, names_by_folder_ids=names_by_folder_ids
            ))

        product_ids = {
            product_entity["id"]
            for product_entity in product_entities
        }

        last_versions_by_product_id = ayon_api.get_last_versions(
            project_name, product_ids, fields={"version"}
        )
        for product_entity in product_entities:
            product_id = product_entity["id"]
            last_version_entity = last_versions_by_product_id.get(product_id)
            if last_version_entity is None:
                continue

            last_version = last_version_entity["version"]
            folder_id = product_entity["folderId"]
            product_name = product_entity["name"]
            _instances = hierarchy[folder_id][product_name]
            for _instance in _instances:
                _instance.data["latestVersion"] = last_version

    def fill_anatomy_data(self, context):
        self.log.debug("Storing anatomy data to instance data.")

        project_entity = context.data["projectEntity"]
        task_types_by_name = {
            task_type["name"]: task_type
            for task_type in project_entity["taskTypes"]
        }

        for instance in context:
            anatomy_data = copy.deepcopy(context.data["anatomyData"])
            product_name = instance.data["productName"]
            product_type = instance.data["productType"]
            anatomy_data.update({
                "family": product_type,
                "subset": product_name,
                "product": {
                    "name": product_name,
                    "type": product_type,
                }
            })

            self._fill_folder_data(instance, project_entity, anatomy_data)
            self._fill_task_data(instance, task_types_by_name, anatomy_data)

            # Define version
            version_number = None
            if self.follow_workfile_version:
                version_number = context.data("version")

            # Even if 'follow_workfile_version' is enabled, it may not be set
            #   because workfile version was not collected to 'context.data'
            # - that can happen e.g. in 'traypublisher' or other hosts without
            #   a workfile
            if version_number is None:
                version_number = instance.data.get("version")

            # use latest version (+1) if already any exist
            if version_number is None:
                latest_version = instance.data["latestVersion"]
                if latest_version is not None:
                    version_number = int(latest_version) + 1

            # If version is not specified for instance or context
            if version_number is None:
                task_data = anatomy_data.get("task") or {}
                task_name = task_data.get("name")
                task_type = task_data.get("type")
                version_number = get_versioning_start(
                    context.data["projectName"],
                    instance.context.data["hostName"],
                    task_name=task_name,
                    task_type=task_type,
                    product_type=instance.data["productType"],
                    product_name=instance.data["productName"]
                )
            anatomy_data["version"] = version_number

            # Additional data
            resolution_width = instance.data.get("resolutionWidth")
            if resolution_width:
                anatomy_data["resolution_width"] = resolution_width

            resolution_height = instance.data.get("resolutionHeight")
            if resolution_height:
                anatomy_data["resolution_height"] = resolution_height

            pixel_aspect = instance.data.get("pixelAspect")
            if pixel_aspect:
                anatomy_data["pixel_aspect"] = float(
                    "{:0.2f}".format(float(pixel_aspect))
                )

            fps = instance.data.get("fps")
            if fps:
                anatomy_data["fps"] = float("{:0.2f}".format(float(fps)))

            # Store anatomy data
            instance.data["projectEntity"] = project_entity
            instance.data["anatomyData"] = anatomy_data
            instance.data["version"] = version_number

            # Log collected data
            instance_name = instance.data["name"]
            instance_label = instance.data.get("label")
            if instance_label:
                instance_name += " ({})".format(instance_label)
            self.log.debug("Anatomy data for instance {}: {}".format(
                instance_name,
                json.dumps(anatomy_data, indent=4)
            ))

    def _fill_folder_data(self, instance, project_entity, anatomy_data):
        # QUESTION should we make sure that all folder data are poped if
        #   folder data cannot be found?
        # - 'folder', 'hierarchy', 'parent', 'folder'
        folder_entity = instance.data.get("folderEntity")
        if folder_entity:
            folder_name = folder_entity["name"]
            folder_path = folder_entity["path"]
            hierarchy_parts = folder_path.split("/")
            hierarchy_parts.pop(0)
            hierarchy_parts.pop(-1)
            parent_name = project_entity["name"]
            if hierarchy_parts:
                parent_name = hierarchy_parts[-1]

            hierarchy = "/".join(hierarchy_parts)
            anatomy_data.update({
                "asset": folder_name,
                "hierarchy": hierarchy,
                "parent": parent_name,
                "folder": {
                    "name": folder_name,
                },
            })
            return

        if instance.data.get("newAssetPublishing"):
            hierarchy = instance.data["hierarchy"]
            anatomy_data["hierarchy"] = hierarchy

            parent_name = project_entity["name"]
            if hierarchy:
                parent_name = hierarchy.split("/")[-1]

            folder_name = instance.data["folderPath"].split("/")[-1]
            anatomy_data.update({
                "asset": folder_name,
                "hierarchy": hierarchy,
                "parent": parent_name,
                "folder": {
                    "name": folder_name,
                },
            })

    def _fill_task_data(self, instance, task_types_by_name, anatomy_data):
        # QUESTION should we make sure that all task data are poped if task
        #   data cannot be resolved?
        # - 'task'

        # Skip if there is no task
        task_name = instance.data.get("task")
        if not task_name:
            return

        # Find task data based on folder entity
        task_entity = instance.data.get("taskEntity")
        task_data = self._get_task_data_from_entity(
            task_entity, task_types_by_name
        )
        if task_data:
            # Fill task data
            # - if we're in editorial, make sure the task type is filled
            if (
                not instance.data.get("newAssetPublishing")
                or task_data["type"]
            ):
                anatomy_data["task"] = task_data
                return

        # New hierarchy is not created, so we can only skip rest of the logic
        if not instance.data.get("newAssetPublishing"):
            return

        # Try to find task data based on hierarchy context and folder path
        hierarchy_context = instance.context.data.get("hierarchyContext")
        folder_path = instance.data.get("folderPath")
        if not hierarchy_context or not folder_path:
            return

        project_name = instance.context.data["projectName"]
        if "/" not in folder_path:
            tasks_info = self._find_tasks_info_in_hierarchy(
                hierarchy_context, folder_path
            )
        else:
            current_data = hierarchy_context.get(project_name, {})
            for key in folder_path.split("/"):
                if key:
                    current_data = (
                        current_data
                        .get("children", {})
                        .get(key, {})
                    )
            tasks_info = current_data.get("tasks", {})

        task_info = tasks_info.get(task_name, {})
        task_type = task_info.get("type")
        task_code = (
            task_types_by_name
            .get(task_type, {})
            .get("shortName")
        )
        anatomy_data["task"] = {
            "name": task_name,
            "type": task_type,
            "short": task_code
        }

    def _get_task_data_from_entity(
        self, task_entity, task_types_by_name
    ):
        """

        Args:
            task_entity (Union[dict[str, Any], None]): Task entity.
            task_types_by_name (dict[str, dict[str, Any]]): Project task
                types.

        Returns:
            Union[dict[str, str], None]: Task data or None if not found.
        """

        if not task_entity:
            return None

        task_type = task_entity["taskType"]
        task_code = (
            task_types_by_name
            .get(task_type, {})
            .get("shortName")
        )
        return {
            "name": task_entity["name"],
            "type": task_type,
            "short": task_code
        }

    def _find_tasks_info_in_hierarchy(self, hierarchy_context, folder_name):
        """Find tasks info for an asset in editorial hierarchy.

        Args:
            hierarchy_context (dict[str, Any]): Editorial hierarchy context.
            folder_name (str): Folder name.

        Returns:
            dict[str, dict[str, Any]]: Tasks info by name.
        """

        hierarchy_queue = collections.deque()
        hierarchy_queue.append(copy.deepcopy(hierarchy_context))
        while hierarchy_queue:
            item = hierarchy_queue.popleft()
            if folder_name in item:
                return item[folder_name].get("tasks") or {}

            for subitem in item.values():
                hierarchy_queue.extend(subitem.get("children") or [])
        return {}
