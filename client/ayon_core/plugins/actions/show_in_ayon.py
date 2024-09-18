import os
import urllib.parse
import webbrowser

from ayon_core.pipeline import LauncherAction
from ayon_core.resources import get_ayon_icon_filepath
import ayon_api


def get_ayon_entity_uri(
    project_name,
    entity_id,
    entity_type,
) -> str:
    """Resolve AYON Entity URI from representation context.

    Note:
        The representation context is the `get_representation_context` dict
        containing the `project`, `folder, `representation` and so forth.
        It is not the representation entity `context` key.

    Arguments:
        project_name (str): The project name.
        entity_id (str): The entity UUID.
        entity_type (str): The entity type, like "folder" or"task".

    Raises:
        RuntimeError: Unable to resolve to a single valid URI.

    Returns:
        str: The AYON entity URI.

    """
    response = ayon_api.post(
        f"projects/{project_name}/uris",
        entityType=entity_type,
        ids=[entity_id])
    if response.status_code != 200:
        raise RuntimeError(
            f"Unable to resolve AYON entity URI for '{project_name}' "
            f"{entity_type} id '{entity_id}': {response.text}"
        )
    uris = response.data["uris"]
    if len(uris) != 1:
        raise RuntimeError(
            f"Unable to resolve AYON entity URI for '{project_name}' "
            f"{entity_type} id '{entity_id}' to single URI. "
            f"Received data: {response.data}"
        )
    return uris[0]["uri"]


class ShowInAYON(LauncherAction):
    """Open AYON browser page to the current context."""
    name = "showinayon"
    label = "Show in AYON"
    icon = get_ayon_icon_filepath()
    order = 999

    def process(self, selection, **kwargs):
        url = os.environ["AYON_SERVER_URL"]
        if selection.is_project_selected:
            project_name = selection.project_name
            url += f"/projects/{project_name}/browser"

            # Specify entity URI if task or folder is select
            entity = None
            entity_type = None
            if selection.is_task_selected:
                entity = selection.get_task_entity()
                entity_type = "task"
            elif selection.is_folder_selected:
                entity = selection.get_folder_entity()
                entity_type = "folder"

            if entity and entity_type:
                uri = get_ayon_entity_uri(
                    project_name,
                    entity_id=entity["id"],
                    entity_type=entity_type
                )
                uri_encoded = urllib.parse.quote_plus(uri)
                url += f"?uri={uri_encoded}"

        # Open URL in webbrowser
        self.log.info(f"Opening URL: {url}")
        webbrowser.open_new_tab(url)
