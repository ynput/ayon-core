#zscript command etc.
import os
import tempfile
import logging
from ayon_core.client import (
    get_project,
    get_asset_by_name,
)
from ayon_core.pipeline import Anatomy, registered_host
from string import Formatter
from . import CommunicationWrapper
from ayon_core.pipeline.template_data import get_template_data


log = logging.getLogger("zbrush.lib")


def execute_zscript(zscript, communicator=None):
    if not communicator:
        communicator = CommunicationWrapper.communicator
    return communicator.execute_zscript(zscript)


def find_first_filled_path(path):
    if not path:
        return ""

    fields = set()
    for item in Formatter().parse(path):
        _, field_name, format_spec, conversion = item
        if not field_name:
            continue
        conversion = "!{}".format(conversion) if conversion else ""
        format_spec = ":{}".format(format_spec) if format_spec else ""
        orig_key = "{{{}{}{}}}".format(
            field_name, conversion, format_spec)
        fields.add(orig_key)

    for field in fields:
        path = path.split(field, 1)[0]
    return path


def get_workdir(project_name, asset_name, task_name):
    project = get_project(project_name)
    asset = get_asset_by_name(project_name, asset_name)

    data = get_template_data(project, asset, task_name)

    anatomy = Anatomy(project_name)
    workdir = anatomy.templates_obj["work"]["folder"].format(data)

    # Remove any potential un-formatted parts of the path
    valid_workdir = find_first_filled_path(workdir)

    # Path is not filled at all
    if not valid_workdir:
        raise AssertionError("Failed to calculate workdir.")

    # Normalize
    valid_workdir = os.path.normpath(valid_workdir)
    if os.path.exists(valid_workdir):
        return valid_workdir

    data.pop("task", None)
    workdir = anatomy.templates_obj["work"]["folder"].format(data)
    valid_workdir = find_first_filled_path(workdir)
    if valid_workdir:
        # Normalize
        valid_workdir = os.path.normpath(valid_workdir)
        if os.path.exists(valid_workdir):
            return valid_workdir


def get_current_file():
    host = registered_host()
    return host.get_current_workfile()


def execute_publish_model_with_dialog(filepath):
    import time
    save_file_zscript = ("""
[IFreeze,
[VarSet, filepath, "{filepath}"]
[FileNameSetNext, #filepath]
[IKeyPress, 13, [IPress, Tool:Export]]]
[Sleep, 2]
]
""").format(filepath=filepath)
    execute_zscript(save_file_zscript)
    time.sleep(8)


def execute_publish_model(filepath):
    save_file_zscript = ("""
[IFreeze,
[VarSet, filepath, "{filepath}"]
[FileNameSetNext, #filepath]
[IKeyPress, 13, [IPress, Tool:Export]]]
]
""").format(filepath=filepath)
    execute_zscript(save_file_zscript)


def is_in_edit_mode():
    """Return whether transform edit mode is currently enabled.

    Certain actions can't be performed if Zbrush is currently within
    edit mode, like exporting a model.

    Returns:
        bool: Whether Edit Mode is enabled.
    """
    tmp_output_file = tempfile.NamedTemporaryFile(
        mode="w", prefix="a_zb_", suffix=".txt", delete=False
    )
    tmp_output_file.close()
    temp_file = tmp_output_file.name.replace("\\", "/")

    in_edit_mode = ("""
[IFreeze,
[MemCreate, EditMode, 20, 0]
[VarSet, InEditMode, [IGet, Transform:Edit]]
[Note, InEditMode]
[MemWriteString, EditMode, #InEditMode, 0]
[MemSaveToFile, EditMode, "{temp_file}", 0]
[MemDelete, EditMode]
]
""").format(temp_file=temp_file)
    execute_zscript(in_edit_mode)
    with open(temp_file) as mode:
        content = str(mode.read())
        bool_mode = content.rstrip('\x00')
        return bool_mode
