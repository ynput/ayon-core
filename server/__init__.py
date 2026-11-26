from typing import Any
from ayon_server.actions import (
    ActionExecutor,
    ExecuteResponseModel,
    SimpleActionManifest,
)
from ayon_server.addons import BaseServerAddon
from ayon_server.api.dependencies import CurrentUser
from ayon_server.access.utils import ensure_entity_access
from ayon_server.entities import ProjectEntity
from ayon_server.exceptions import ForbiddenException
from ayon_server.types import OPModel
from ayon_server.lib.postgres import Postgres
from ayon_server.events import dispatch_event

try:
    from ayon_server.logging import logger
except ImportError:
    from nxtools import logging as logger

from .settings import (
    CoreSettings,
    DEFAULT_VALUES,
    convert_settings_overrides,
)


class CleanupFolderThumbnailsRequestModel(OPModel):
    folder_ids: list[str]


class CleanupFolderThumbnailsResponseModel(OPModel):
    count: int


class CoreAddon(BaseServerAddon):
    settings_model = CoreSettings

    async def get_default_settings(self):
        settings_model_cls = self.get_settings_model()
        return settings_model_cls(**DEFAULT_VALUES)

    async def convert_settings_overrides(
        self,
        source_version: str,
        overrides: dict[str, Any],
    ) -> dict[str, Any]:
        convert_settings_overrides(source_version, overrides)
        # Use super conversion
        return await super().convert_settings_overrides(
            source_version, overrides
        )

    def initialize(self) -> None:
        self.add_endpoint(
            "cleanupFolderThumbnails/{project_name}",
            self._cleanup_folder_thumbnails,
            method="POST",
        )

    async def get_simple_actions(
        self,
        project_name: str | None = None,
        variant: str = "production",
    ) -> list[SimpleActionManifest]:
        """Return a list of simple actions provided by the addon"""
        output = []

        if project_name:
            # Add 'Create Project Folder Structure' action to folders.
            output.append(
                SimpleActionManifest(
                    identifier="core.createprojectstructure",
                    label="Create Project Folder Structure",
                    icon={
                        "type": "material-symbols",
                        "name": "create_new_folder",
                    },
                    order=100,
                    entity_type="project",
                    entity_subtypes=None,
                    allow_multiselection=False,
                )
            )
            output.append(
                SimpleActionManifest(
                    identifier="core.delivery.version",
                    label="Deliver versions (launcher action)",
                    icon={
                        "type": "material-symbols",
                        "name": "create_new_folder",
                    },
                    order=100,
                    entity_type="version",
                    entity_subtypes=None,
                    allow_multiselection=True,
                )
            )
            output.append(
                SimpleActionManifest(
                    identifier="core.delivery.list",
                    label="Deliver versions (launcher action)",
                    icon={
                        "type": "material-symbols",
                        "name": "create_new_folder",
                    },
                    order=100,
                    entity_type="list",
                    entity_subtypes=[
                        "version:review-session",
                        "version:generic",
                    ],
                    allow_multiselection=False,
                )
            )

        return output

    async def execute_action(
        self,
        executor: ActionExecutor,
    ) -> ExecuteResponseModel:
        """Execute webactions."""

        project_name = executor.context.project_name

        if executor.identifier == "core.createprojectstructure":
            if not project_name:
                logger.error(
                    f"Can't execute {executor.identifier} because"
                    " of missing project name."
                )
                # Works since AYON server 1.8.3
                if hasattr(executor, "get_simple_response"):
                    return await executor.get_simple_response(
                        "Missing project name", success=False
                    )
                return

            args = [
                "create-project-structure", "--project", project_name,
            ]
            # Works since AYON server 1.8.3
            if hasattr(executor, "get_launcher_response"):
                return await executor.get_launcher_response(args)

            return await executor.get_launcher_action_response(args)

        if executor.identifier == "core.delivery.version":
            selected_versions = await executor.context.get_entities()
            if not selected_versions:
                return await executor.get_server_action_response(
                    message="No versions available in selection.",
                    success=False
                )
            version_ids = [version.id for version in selected_versions]
            event_id = await dispatch_event(
                topic="delivery.requested",
                project=project_name,
                payload={"version_ids": version_ids},
                finished=True,
            )
            args = [
                "deliver", "--project", project_name,
                "--event_id", event_id,
            ]

            return await executor.get_launcher_response(args)

        if executor.identifier == "core.delivery.list":
            if not executor.context.entity_ids:
                return await executor.get_server_action_response(
                    message="No list selected.",
                    success=False
                )

            selected_list = executor.context.entity_ids[0]
            event_id = await dispatch_event(
                topic="delivery.requested",
                project=project_name,
                payload={"list_id": selected_list},
                finished=True,
            )
            args = [
                "deliver", "--project", project_name,
                "--event_id", event_id,
            ]

            return await executor.get_launcher_response(args)

        logger.debug(f"Unknown action: {executor.identifier}")

        if hasattr(executor, "get_simple_response"):
            return await executor.get_simple_response(
                "Unknown action", success=False
            )

    async def _cleanup_folder_thumbnails(
        self,
        user: CurrentUser,
        project_name: str,
        payload: CleanupFolderThumbnailsRequestModel,
    ) -> CleanupFolderThumbnailsResponseModel:
        """Remove thumbnail ids from folders sharing thumbnail with a version.

        User must be able to publish to, or update, all passed folders.

        Args:
            project_name (str): Name of the project.
            payload (CleanupFolderThumbnailsRequestModel): Request payload
                containing folder ids.

        """
        # Validate the project exists
        _project = await ProjectEntity.load(project_name)

        # Validate user has permissions to access the project
        await user.ensure_project_access(project_name)

        folder_ids = list(set(payload.folder_ids))
        if not folder_ids:
            return CleanupFolderThumbnailsResponseModel(count=0)

        await _ensure_folders_thumbnail_access(user, project_name, folder_ids)

        async with Postgres.transaction():
            res = await Postgres.fetch(
                UPDATE_THUMBNAILS_BY_IDS_QUERY.format(
                    project_name=project_name
                ),
                folder_ids,
            )
            filtered_folder_ids = [row["id"] for row in res]

        return CleanupFolderThumbnailsResponseModel(
            count=len(filtered_folder_ids)
        )


def _supports_multi_entity_access() -> bool:
    """Server 1.16.4+ can validate access of multiple entities at once."""
    try:
        from ayon_server.version import __version__ as server_version

        version = tuple(
            int(part) for part in server_version.split("-")[0].split(".")[:3]
        )
    except Exception:
        return False
    return version >= (1, 16, 4)


async def _ensure_folders_access(
    user, project_name: str, folder_ids: list[str], access_type: str
) -> None:
    if _supports_multi_entity_access():
        await ensure_entity_access(
            user, project_name, "folder", folder_ids, access_type
        )
        return

    # Older servers support only a single entity id
    for folder_id in folder_ids:
        await ensure_entity_access(
            user, project_name, "folder", folder_id, access_type
        )


async def _ensure_folders_thumbnail_access(
    user, project_name: str, folder_ids: list[str]
) -> None:
    """Make sure user can change thumbnail of all passed folders.

    Same rules as server uses for folder thumbnail update, publish
        access is enough, otherwise update access is required.

    Raises:
        ForbiddenException: User can't change thumbnail of some folders.

    """
    if user.is_manager:
        return

    try:
        await _ensure_folders_access(
            user, project_name, folder_ids, "publish"
        )
    except ForbiddenException:
        await _ensure_folders_access(
            user, project_name, folder_ids, "update"
        )


UPDATE_THUMBNAILS_BY_IDS_QUERY = """
UPDATE project_{project_name}.folders AS f
SET thumbnail_id = NULL
WHERE f.thumbnail_id IS NOT NULL
    AND f.id = ANY($1)
    AND EXISTS (
        SELECT 1
        FROM project_{project_name}.versions AS v
        WHERE v.thumbnail_id = f.thumbnail_id
    )
RETURNING f.id AS id;
"""
