import os
import urllib.parse
import webbrowser

from ayon_core.pipeline import LauncherAction
from ayon_core.resources import get_ayon_icon_filepath


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
            url += f"/projects/{project_name}/overview"

            query = {
                "project": project_name
            }
            if selection.is_task_selected:
                query["type"] = "task"
                query["id"] = selection.get_task_entity()["id"]
            elif selection.is_folder_selected:
                query["type"] = "folder"
                query["id"] = selection.get_folder_entity()["id"]

            url += f"?{urllib.parse.urlencode(query)}"

        # Open URL in webbrowser
        self.log.info(f"Opening URL: {url}")
        webbrowser.open_new_tab(url)
