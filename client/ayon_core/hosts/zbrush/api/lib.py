#zscript command etc.
import os
import uuid
import time
import tempfile
import logging
from ayon_core.client import (
    get_project,
    get_asset_by_name,
)
from ayon_core.pipeline import Anatomy
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


def execute_zscript_and_wait(zscript, path, wait=0.1, timeout=20):
    """Execute zscript and wait until zscript finished processing"""
    execute_zscript(zscript)

    # Wait around until the zscript finished
    time_taken = 0
    while not os.path.exists(path):
        time.sleep(wait)
        time_taken += wait
        if time_taken > timeout:
            raise RuntimeError(
                f"Timeout. Zscript took longer than "
                "{timeout}s to run."
            )

def execute_publish_model_with_dialog(filepath):
    save_file_zscript = ("""
[IFreeze,
[VarSet, filepath, "{filepath}"]
[FileNameSetNext, #filepath]
[IKeyPress, 13, [IPress, Tool:Export]]]
[Sleep, 2]
]
""").format(filepath=filepath)
    execute_zscript_and_wait(save_file_zscript, filepath)


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
    identifier = uuid.uuid4()
    temp_path = os.path.join(
        tempfile.gettempdir(),
        f"{tempfile.gettempprefix()}_{identifier}.txt"
    )
    temp_path = temp_path.replace("\\", "/")
    assert not os.path.exists(temp_path)

    in_edit_mode = ("""
[IFreeze,
[MemCreate, EditMode, 20, 0]
[VarSet, InEditMode, [IGet, Transform:Edit]]
[Note, InEditMode]
[MemWriteString, EditMode, #InEditMode, 0]
[MemSaveToFile, EditMode, "{temp_file}", 1]
[MemDelete, EditMode]
]
""").format(temp_file=temp_path)
    execute_zscript_and_wait(in_edit_mode, temp_path)
    with open(temp_path) as mode:
        content = str(mode.read())
        bool_mode = content.rstrip('\x00')
        return bool_mode

# TODO: add the zscript code
# Current file