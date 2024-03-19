import os

import pyblish.api
import pyblish.util

from ayon_api import get_folder_by_name
from ayon_core.lib.attribute_definitions import FileDefItem
from ayon_core.pipeline import install_host
from ayon_core.pipeline.create import CreateContext

from ayon_core.hosts.traypublisher.api import TrayPublisherHost


def csvpublish(
    filepath,
    project_name,
    folder_name,
    task_name=None,
    ignore_validators=False
):
    """Publish CSV file.

    Args:
        filepath (str): Path to CSV file.
        project_name (str): Project name.
        folder_name (str): Folder name.
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
    asset_doc = get_folder_by_name(
        project_name,
        folder_name=folder_name
    )

    create_context.create(
        "io.ayon.creators.traypublisher.csv_ingest",
        "Main",
        asset_doc=asset_doc,
        task_name=task_name,
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
