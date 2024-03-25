"""
Provides:
    context -> projectName (str)
    context -> folderPath (str)
    context -> task (str)
"""

import pyblish.api
from ayon_core.pipeline import get_current_context


class CollectCurrentContext(pyblish.api.ContextPlugin):
    """Collect project context into publish context data.

    Plugin does not override any value if is already set.
    """

    order = pyblish.api.CollectorOrder - 0.5
    label = "Collect Current context"

    def process(self, context):
        # Check if values are already set
        project_name = context.data.get("projectName")
        folder_path = context.data.get("folderPath")
        task_name = context.data.get("task")

        current_context = get_current_context()
        if not project_name:
            context.data["projectName"] = current_context["project_name"]

        if not folder_path:
            context.data["folderPath"] = current_context["folder_path"]

        if not task_name:
            context.data["task"] = current_context["task_name"]

        # QUESTION should we be explicit with keys? (the same on instances)
        #   - 'task' -> 'taskName'

        self.log.info((
            "Collected project context\n"
            "Project: {project_name}\n"
            "Folder: {folder_path}\n"
            "Task: {task_name}"
        ).format(
            project_name=context.data["projectName"],
            folder_path=context.data["folderPath"],
            task_name=context.data["task"]
        ))
