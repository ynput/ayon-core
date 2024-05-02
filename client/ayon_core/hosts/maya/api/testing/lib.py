import os
import traceback

import ayon_api
from ayon_core.pipeline import (
    get_current_project_name,
    Anatomy,
    get_current_context,
    get_current_host_name,
    registered_host
)
from ayon_core.pipeline.workfile import (
    get_last_workfile_with_version, get_workfile_template_key
)
from ayon_api import get_folder_by_path, get_task_by_name
from ayon_core.pipeline.template_data import (
    get_template_data,
    get_task_template_data,
    get_folder_template_data,
)

from .tests import test_create, test_publish, test_load


def _save_repository_workfile():
    # Get new workfile version path.
    project_name = get_current_project_name()
    anatomy = Anatomy(project_name)
    current_context = get_current_context()
    folder = get_folder_by_path(
        project_name,
        current_context["folder_path"],
    )
    task = get_task_by_name(
        project_name,
        folder["id"],
        current_context["task_name"]
    )
    category_name = get_workfile_template_key(
        project_name,
        task["taskType"],
        get_current_host_name(),
    )
    template_info = anatomy.get_template_item(category_name, "default")
    directory_template = template_info["directory"]
    project = ayon_api.get_project(project_name)
    fill_data = get_template_data(project)
    fill_data.update(get_folder_template_data(folder, project_name))
    fill_data.update(get_task_template_data(project, task))
    workdir = directory_template.format_strict(fill_data).normalized()
    extensions = ["ma", "mb"]
    workfile, version = get_last_workfile_with_version(
        str(workdir), str(template_info["file"]), fill_data, extensions
    )
    fill_data["version"] = version + 1
    fill_data["ext"] = os.path.splitext(workfile)[1][1:]
    workfile = template_info["file"].format_strict(fill_data).normalized()
    workfile_path = os.path.join(workdir, workfile)

    host = registered_host()
    host.open_file(os.path.join(os.path.dirname(__file__), "tests.ma"))
    host.save_file(workfile_path)


def run_tests():
    try:
        test_create()
        test_publish()
        test_load()
    except Exception as e:
        traceback.print_exc()
        raise(e)
    print("Testing was successfull!")


def run_tests_on_repository_workfile():
    try:
        _save_repository_workfile()
        run_tests()
    except Exception as e:
        traceback.print_exc()
        raise(e)


def test_create_on_repository_workfile():
    try:
        _save_repository_workfile()
        test_create()
    except Exception as e:
        traceback.print_exc()
        raise(e)


def test_publish_on_repository_workfile():
    try:
        _save_repository_workfile()
        test_publish()
    except Exception as e:
        traceback.print_exc()
        raise(e)


def test_load_on_repository_workfile():
    try:
        _save_repository_workfile()
        test_publish()
    except Exception as e:
        traceback.print_exc()
        raise(e)
