from ayon_core.pipeline import LauncherAction, project_folders


class CreateProjectFoldersAction(LauncherAction):
    """Create project folders as defined in settings."""
    name = "create_project_folders"
    label = "Create Project Folders"
    icon = "sitemap"
    color = "#e0e1e1"
    order = 1000

    def is_compatible(self, selection) -> bool:

        # Disable when the project folder structure setting is empty
        # in settings
        project_settings = selection.get_project_settings()
        folder_structure = (
            project_settings["core"]["project_folder_structure"]
        ).strip()
        if not folder_structure or folder_structure == "{}":
            return False

        return (
            selection.is_project_selected
            and not selection.is_folder_selected
        )

    def process(self, selection, **kwargs):
        project_folders.create_project_folders(selection.project_name)
