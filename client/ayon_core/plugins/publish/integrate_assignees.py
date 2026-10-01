"""Integrate collected reviewers onto the tasks of published versions."""

from __future__ import annotations

import pyblish.api
from ayon_api.operations import OperationsSession


class IntegrateAssignees(pyblish.api.ContextPlugin):
    """Assign reviewers collected by 'CollectAssignees' to the task.

    ``assignees`` is a task level field in AYON, a version only points to
    its task. The reviewers picked in the publisher are therefore written
    onto the task entity the published versions belong to, so they show up
    in the task assignee UI, filters and notifications.
    """

    order = pyblish.api.IntegratorOrder + 0.6
    label = "Integrate Assignees"

    def process(self, context: pyblish.api.Context) -> None:
        project_name = context.data.get("projectName")
        if not project_name:
            self.log.warning(
                "Skipping assignees integration, context has no project."
            )
            return

        # task id -> assignees to set, and the current server value
        pending: dict[str, list[str]] = {}
        original: dict[str, list[str]] = {}

        for instance in context:
            assignees = instance.data.get("assignees")
            if not assignees:
                continue

            task_entity = instance.data.get("taskEntity")
            if not task_entity:
                self.log.warning(
                    "Instance '{}' has assignees but no task, skipping."
                    .format(instance.data.get("name") or instance.name)
                )
                continue

            task_id = task_entity["id"]
            if task_id not in original:
                original[task_id] = list(
                    task_entity.get("assignees") or []
                )

            # Multiple instances can share one task, merge them all.
            merged = list(pending.get(task_id, original[task_id]))
            merged += list(assignees)

            # keep order, drop duplicates
            pending[task_id] = list(dict.fromkeys(merged))

        updates = {
            task_id: assignees
            for task_id, assignees in pending.items()
            if assignees != original[task_id]
        }
        if not updates:
            self.log.debug("No task assignees to integrate.")
            return

        op_session = OperationsSession()
        for task_id, assignees in updates.items():
            op_session.update_entity(
                project_name, "task", task_id, {"assignees": assignees}
            )

        try:
            op_session.commit()
        except Exception as exc:
            # Changing task assignees needs a dedicated permission, which
            # artists may not have. Never fail the whole publish for it.
            self.log.warning(
                "Failed to assign reviewers to task(s)",
                exc_info=True,
            )
            return

        self.log.info(f"Updated assignees on {len(updates)} task(s).")
