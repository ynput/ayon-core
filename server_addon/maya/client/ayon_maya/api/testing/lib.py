import os
import traceback

import pyblish.api

import ayon_api
from ayon_core.pipeline import (
    get_current_project_name,
    Anatomy,
    get_current_context,
    get_current_host_name,
    registered_host
)
from ayon_core.pipeline.create import CreateContext
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


def recursive_validate(valid_action_names):
    """Recursively validate until it is either successful or there are
    no more approved actions to run in which case its failing.
    """
    context = pyblish.api.Context()
    context.data["create_context"] = CreateContext(registered_host())
    context = pyblish.util.collect(context)
    pyblish.util.validate(context)

    success = True
    actions_executed = []
    action_errors = []
    for result in context.data["results"]:
        if result["success"]:
            continue

        success = False

        for action in result["plugin"].actions:
            if action.__name__ not in valid_action_names:
                continue
            actions_executed.append(action)
            try:
                action().process(context, result["plugin"])
            except Exception:
                action_errors.append(traceback.format_exc())

    if action_errors:
        context.data["action_errors"] = action_errors
        return False, context

    if not success and not actions_executed:
        return False, context

    if success:
        return True, context

    return recursive_validate(valid_action_names)


def create_error_report(context):
    error_message = ""
    for result in context.data["results"]:
        if result["success"]:
            continue

        err = result["error"]
        formatted_traceback = "".join(
            traceback.format_exception(
                type(err),
                err,
                err.__traceback__
            )
        )
        fname = result["plugin"].__module__
        if 'File "<string>", line' in formatted_traceback:
            _, lineno, func, msg = err.traceback
            fname = os.path.abspath(fname)
            formatted_traceback = formatted_traceback.replace(
                'File "<string>", line',
                'File "{0}", line'.format(fname)
            )

        err = result["error"]
        error_message += "\n"
        error_message += formatted_traceback

    error_message += "\n".join(context.data.get("action_errors", []))

    return error_message


def run_tests():
    try:
        test_create()
        test_publish()
        test_load()
    except Exception as e:
        traceback.print_exc()
        raise(e)
    print("Testing was successful!")


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
