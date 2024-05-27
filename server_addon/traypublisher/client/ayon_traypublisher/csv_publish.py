import pyblish.api
import pyblish.util

from ayon_api import get_folder_by_path, get_task_by_name
from ayon_core.lib.attribute_definitions import FileDefItem
from ayon_core.pipeline import install_host
from ayon_core.pipeline.create import CreateContext

from ayon_traypublisher.api import TrayPublisherHost


def csvpublish(
    filepath,
    project_name,
    folder_path,
    task_name=None,
    ignore_validators=False
):
    """Publish CSV file.

    Args:
        filepath (str): Path to CSV file.
        project_name (str): Project name.
        folder_path (str): Folder path.
        task_name (Optional[str]): Task name.
        ignore_validators (Optional[bool]): Option to ignore validators.
    """

    # initialization of host
    host = TrayPublisherHost()
    install_host(host)

    # setting host context into project
    host.set_project_name(project_name)

    # form precreate data with field values
    file_field = FileDefItem.from_paths([filepath], False).pop().to_dict()
    precreate_data = {
        "csv_filepath_data": file_field,
    }

    # create context initialization
    create_context = CreateContext(host, headless=True)
    folder_entity = get_folder_by_path(
        project_name,
        folder_path=folder_path,
    )

    if not folder_entity:
        ValueError(
            f"Folder path '{folder_path}' doesn't "
            f"exists at project '{project_name}'."
        )

    task_entity = get_task_by_name(
        project_name,
        folder_entity["id"],
        task_name,
    )

    if not task_entity:
        ValueError(
            f"Task name '{task_name}' doesn't "
            f"exists at folder '{folder_path}'."
        )

    create_context.create(
        "io.ayon.creators.traypublisher.csv_ingest",
        "Main",
        folder_entity=folder_entity,
        task_entity=task_entity,
        pre_create_data=precreate_data,
    )

    # publishing context initialization
    pyblish_context = pyblish.api.Context()
    pyblish_context.data["create_context"] = create_context

    # redefine targets (skip 'local' to disable validators)
    if ignore_validators:
        targets = ["default", "ingest"]

    # publishing
    pyblish.util.publish(context=pyblish_context, targets=targets)
