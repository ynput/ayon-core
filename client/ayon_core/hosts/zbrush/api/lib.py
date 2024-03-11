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


def get_tempfile_path() -> str:
    """Return a path valid to write a tempfile to that does not exist yet.

    This can be, for example, used as temporary path to allow a ZScript to
    to store variable values into as a return value to Python.
    """
    identifier = uuid.uuid4()
    temp_path = os.path.join(
        tempfile.gettempdir(),
        f"{tempfile.gettempprefix()}_{identifier}.txt"
    )
    assert not os.path.exists(temp_path)
    return temp_path


def execute_zscript(zscript, communicator=None):
    """Execute ZScript.

    Note that this will *not* wait around for the ZScript to run or for its
    completion. Nor will errors in the script be detected or raised.

    """
    if not communicator:
        communicator = CommunicationWrapper.communicator
    print(f"Executing ZScript: {zscript}")
    return communicator.execute_zscript(zscript)


def execute_zscript_and_wait(zscript,
                             check_filepath=None,
                             sub_level=0,
                             wait=0.1,
                             timeout=20):
    """Execute ZScript and wait until ZScript finished processing.

    This actually waits until a particular file exists on disk. If your ZScript
    is solely intended to write out to a file to return a variable value from
    ZBrush then you can set `check_filepath` to that file you'll be writing to.
    As soon as that file is found this function will assume the script has
    finished. If no `check_filepath` is provided a few extra lines of ZScript
    will be appended to your

    Warning: If your script errors in Zbrush and thus does not continue to
        write the file then this function will wait around until the timeout.

    Raises:
        RuntimeError: When timeout is reached.

    Args:
        zscript (str): The ZScript to run.
        check_filepath (str): Wait until this filepath exists, otherwise
            wait until the timeout is reached if never found.
        wait (float): The amount of seconds to wait in-between each file
            existence check.
        timeout (float): The amount of seconds after which the script will be
            assumed to have failed and raise an error.

    """
    execute_zscript(zscript)

    # Wait around until the zscript finished
    time_taken = 0
    while not os.path.exists(check_filepath):
        time.sleep(wait)
        time_taken += wait
        if time_taken > timeout:
            raise RuntimeError(
                "Timeout. Zscript took longer than "
                f"{timeout}s to run."
            )


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


def export_tool(filepath: str, sub_level: int):
    """Export active zbrush tool to filepath."""
    filepath = filepath.replace("\\", "/")
    export_tool_zscript = ("""
[IFreeze,
[VarSet, subdlevel, {sub_level}]
[VarSet, maxSubd, [IGetMax, Tool:Geometry:SDiv]]
[If, subdlevel == 0 || sublevel > maxSubd,
[VarSet, subdlevel, maxSubd]]
[ISet, "Tool:Geometry:SDiv", subdlevel, 0]
[FileNameSetNext, "{filepath}"]
[IKeyPress, 13, [IPress, Tool:Export]]
]
""").format(filepath=filepath, sub_level=sub_level)

    # We do not check for the export file's existence because Zbrush might
    # write the file in chunks, as such the file might exist before the writing
    # to it has finished
    execute_zscript_and_wait(
        export_tool_zscript, check_filepath=filepath,
        sub_level=sub_level)


def is_in_edit_mode():
    """Return whether transform edit mode is currently enabled.

    Certain actions can't be performed if Zbrush is currently not within
    edit mode, like exporting a model.

    Returns:
        bool: Whether Edit Mode is enabled.
    """
    temp_path = get_tempfile_path()
    temp_path = temp_path.replace("\\", "/")

    # Write Transform:Edit state to temp file
    in_edit_mode = ("""
[IFreeze,
[MemCreate, EditMode, 20, 0]
[MemWriteString, EditMode, [IGet, Transform:Edit], 0]
[MemSaveToFile, EditMode, "{temp_file}", 1]
[MemDelete, EditMode]
]
""").format(temp_file=temp_path)
    execute_zscript_and_wait(in_edit_mode, temp_path, timeout=3)
    with open(temp_path, "r") as mode:
        content = str(mode.read())
        bool_mode = content.rstrip('\x00')

    return bool_mode


def remove_subtool(basename):
    remove_subtool_zscript = ("""
[VarSet,totalSubtools,[SubToolGetCount]]
[Loop, totalSubtools,
  [SubToolSelect, [Val, n]]
  [VarSet, subtoolName, [IGetTitle, "Tool:ItemInfo"]] // Get the tool name
  [VarSet, subtoolName, [StrExtract, subtoolName, 0, [StrLength, subtoolName] - 2]]
  [VarSet, name,  [StrFind, "{basename}", subtoolName]]
  [Note, name]
  [If, name >= 0,
  [IKeyPress,'3',[IPress,Tool:SubTool:Delete]]
  ]
, n]

""").format(basename=basename)

    execute_zscript(remove_subtool_zscript)
