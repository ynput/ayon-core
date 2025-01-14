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

from ayon_core.pipeline import KnownPublishError


class CollectContextEntities(pyblish.api.ContextPlugin):
    """Collect entities into Context."""

    order = pyblish.api.CollectorOrder - 0.1
    label = "Collect Context Entities"

    def process(self, context):
        project_name = context.data["projectName"]
        folder_path = context.data["folderPath"]
        task_name = context.data["task"]

        project_entity = ayon_api.get_project(project_name)
        if not project_entity:
            raise KnownPublishError(
                "Project '{}' was not found.".format(project_name)
            )
        self.log.debug("Collected Project \"{}\"".format(project_entity))

        context.data["projectEntity"] = project_entity

        if not folder_path:
            self.log.info("Context is not set. Can't collect global data.")
            return

        folder_entity = self._get_folder_entity(project_name, folder_path)
        self.log.debug("Collected Folder \"{}\"".format(folder_entity))

        task_entity = self._get_task_entity(
            project_name, folder_entity, task_name
        )
        self.log.debug("Collected Task \"{}\"".format(task_entity))

        context.data["folderEntity"] = folder_entity
        context.data["taskEntity"] = task_entity
        context_attributes = (
            task_entity["attrib"] if task_entity else folder_entity["attrib"]
        )

        # Task type
        task_type = None
        if task_entity:
            task_type = task_entity["taskType"]

        context.data["taskType"] = task_type

        frame_start = context_attributes.get("frameStart")
        if frame_start is None:
            frame_start = 1
            self.log.warning("Missing frame start. Defaulting to 1.")

        frame_end = context_attributes.get("frameEnd")
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
                "Folder '{}' was not found in project '{}'.".format(
                    folder_path, project_name
                )
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
                "Task '{}' was not found in project '{}'.".format(
                    task_path, project_name)
            )
        return task_entity
