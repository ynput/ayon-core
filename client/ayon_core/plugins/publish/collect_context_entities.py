"""Collect Anatomy and global anatomy data.

Requires:
    context -> projectName
    context -> folderPath
    context -> task

Provides:
    context -> projectEntity - Project entity from AYON server.
    context -> folderEntity - Folder entity from AYON server only if
        'folderPath' is set in context data.
    context -> taskEntity - Task entity from AYON server only if 'folderPath'
        and 'task' are set in context data.
"""

import pyblish.api
import ayon_api

from ayon_core.pipeline import KnownPublishError, Anatomy


class CollectContextEntities(pyblish.api.ContextPlugin):
    """Collect entities into Context."""

    order = pyblish.api.CollectorOrder - 0.45
    label = "Collect Context Entities"

    def process(self, context):
        project_name = context.data["projectName"]
        folder_path = context.data["folderPath"]
        task_name = context.data["task"]

        project_entity = context.data.get("projectEntity")
        folder_entity = context.data.get("folderEntity")
        task_entity = context.data.get("taskEntity")

        if not project_entity:
            project_entity = ayon_api.get_project(project_name)
            if not project_entity:
                raise KnownPublishError(
                    f"Project '{project_name}' was not found."
                )

        context.data["projectEntity"] = project_entity
        context.data["anatomy"] = Anatomy(
            project_name, project_entity=project_entity
        )

        self.log.debug(f"Project entity \"{project_entity}\"")

        if not folder_path:
            self.log.info("Context is not set. Can't collect global data.")
            return

        if folder_entity and folder_entity["path"] != folder_path:
            folder_entity = None

        if not folder_entity:
            folder_entity = self._get_folder_entity(project_name, folder_path)

        self.log.debug(f"Folder entity \"{folder_entity}\"")

        if (
            task_entity
            and task_entity["folderId"] != folder_entity["id"]
            and task_entity["name"] != task_name
        ):
            task_entity = None

        if not task_entity:
            task_entity = self._get_task_entity(
                project_name, folder_entity, task_name
            )
        self.log.debug(f"Task entity \"{task_entity}\"")

        context.data["folderEntity"] = folder_entity
        context.data["taskEntity"] = task_entity

        context_attributes = folder_entity["attrib"]
        task_type = None
        if task_entity:
            context_attributes = task_entity["attrib"]
            task_type = task_entity["taskType"]

        context.data["taskType"] = task_type

        frame_start = context_attributes.get("frameStart")
        frame_end = context_attributes.get("frameEnd")
        if frame_start is None:
            frame_start = 1
            self.log.warning("Missing frame start. Defaulting to 1.")

        if frame_end is None:
            frame_end = 2
            self.log.warning("Missing frame end. Defaulting to 2.")

        context.data["frameStart"] = frame_start
        context.data["frameEnd"] = frame_end

        handle_start = context_attributes.get("handleStart") or 0
        handle_end = context_attributes.get("handleEnd") or 0

        context.data["handleStart"] = int(handle_start)
        context.data["handleEnd"] = int(handle_end)

        frame_start_h = frame_start - context.data["handleStart"]
        frame_end_h = frame_end + context.data["handleEnd"]
        context.data["frameStartHandle"] = frame_start_h
        context.data["frameEndHandle"] = frame_end_h

        context.data["fps"] = context_attributes["fps"]

    def _get_folder_entity(self, project_name, folder_path):
        if not folder_path:
            return None
        folder_entity = ayon_api.get_folder_by_path(project_name, folder_path)
        if not folder_entity:
            raise KnownPublishError(
                f"Folder '{folder_path}' was not found"
                f" in project '{project_name}'."
            )
        return folder_entity

    def _get_task_entity(self, project_name, folder_entity, task_name):
        if not folder_entity or not task_name:
            return None
        task_entity = ayon_api.get_task_by_name(
            project_name, folder_entity["id"], task_name
        )
        if not task_entity:
            task_path = "/".join([folder_entity["path"], task_name])
            raise KnownPublishError(
                f"Task '{task_path}' was not found"
                f" in project '{project_name}'."
            )
        return task_entity
