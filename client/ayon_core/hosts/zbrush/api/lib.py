import os
import uuid
import time
import tempfile
import functools
import logging

from . import CommunicationWrapper


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


def wait_zscript(until=None,
                 wait: float = 0.1,
                 ping_wait: float = 2.0,
                 timeout: float = 15.0) -> int:
    """Wait until the condition is met or until zbrush responds again.

    This periodically 'pings' zbrush by submitting a zscript for execution
    that will write a temporary ping file. As soon as that file exists it is
    assumed that Zbrush has responded.

    If the `until` callable is passed, then during the wait this function will
    periodically be called, and when True it's will assume success and stop
    waiting.

    Args:
        until (callable): If a callable is provided, whenever it returns
            True the wait is cancelled and assumed to have finished.
        wait (float): The amount of seconds to wait in-between each file
            existence check.
        ping_wait (float): The amount of seconds between sending a new 'ping'
            whether Zbrush is responding already - usually to detect whether
            a zscript had finished processing.
        timeout (float): The amount of seconds after which the script will be
            assumed to have failed and raise an error.

    Returns:
        int: -1 if callable `until` returned True. Otherwise returns the amount
             of pings that were sent before Zbrush responded.

    """
    # It may occur that a zscript execution gets interrupted and thus a 'ping'
    # gets lost. To avoid just long waits until the timeout in case previous
    # pings got lost we periodically execute a new check ping zscript to see
    # if that finishes rapidly

    ping_filepath = get_tempfile_path().replace("\\", "/")
    var_name = str(uuid.uuid4()).replace("-", "_")
    create_ping_file_zscript = f"""
[MemCreate, "AYON_{var_name}", 1, 0]
[MemWriteString, "AYON_{var_name}", "1", 0]
[MemSaveToFile, "AYON_{var_name}", "{ping_filepath}", 1]
[MemDelete,  "AYON_{var_name}"]
    """
    start_time = time.time()
    timeout_time = start_time + timeout
    last_ping_time = None
    num_pings_sent = 0
    while True:
        if until is not None and until():
            # We have reached the `until` condition
            print("Condition met..")
            return -1

        t = time.time()
        if last_ping_time is None or t - last_ping_time > ping_wait:
            last_ping_time = t
            num_pings_sent += 1
            execute_zscript(create_ping_file_zscript)

        # Check the periodic pings we have sent - check only the last pings
        # up to the max amount.
        if os.path.exists(ping_filepath):
            print(f"Sent {num_pings_sent} pings. "
                  f"Received answer after {t-start_time} seconds.")
            if os.path.isfile(ping_filepath):
                os.remove(ping_filepath)

            return num_pings_sent

        if t > timeout_time:
            raise RuntimeError(
                "Timeout. Zscript took longer than "
                f"{timeout}s to run."
            )

        time.sleep(wait)


def execute_zscript_and_wait(zscript,
                             check_filepath=None,
                             wait: float = 0.1,
                             ping_wait: float = 2.0,
                             timeout: float = 10.0):
    """Execute ZScript and wait until ZScript finished processing.

    This actually waits until a particular file exists on disk. If your ZScript
    is solely intended to write out to a file to return a variable value from
    ZBrush then you can set `check_filepath` to that file you'll be writing to.
    As soon as that file is found this function will assume the script has
    finished. If no `check_filepath` is provided a few extra lines of ZScript
    will be appended to your

    Raises:
        RuntimeError: When timeout is reached.

    Args:
        zscript (str): The ZScript to run.
        check_filepath (str): Wait until this filepath exists, otherwise
            wait until the timeout is reached if never found.
        wait (float): The amount of seconds to wait in-between each file
            existence check.
        ping_wait (float): The amount of seconds between sending a new 'ping'
            whether Zbrush is responding already - usually to detect whether
            a zscript had finished processing.
        timeout (float): The amount of seconds after which the script will be
            assumed to have failed and raise an error.

    """
    if check_filepath is None:
        var_name = str(uuid.uuid4())
        success_check_file = get_tempfile_path().replace("\\", "/")
        zscript += f"""
[MemCreate, "AYON_{var_name}", 1, 0]
[MemWriteString, "AYON_{var_name}", "1", 0]
[MemSaveToFile, "AYON_{var_name}", "{success_check_file}", 1]
[MemDelete,  "AYON_{var_name}"]
        """
    else:
        success_check_file = check_filepath

    def wait_until(filepath):
        if filepath and os.path.exists(filepath):
            return True

    fn = functools.partial(wait_until, check_filepath)

    execute_zscript(zscript)
    wait_zscript(until=fn,
                 wait=wait,
                 ping_wait=ping_wait,
                 timeout=timeout)

    if not os.path.exists(success_check_file):
        raise RuntimeError(
            f"Success file does not exist: {success_check_file}"
        )


def get_workdir() -> str:
    """Return the currently active work directory"""
    return os.environ["AYON_WORKDIR"]


def export_tool(filepath: str, subdivision_level: int = 0):
    """Export active zbrush tool to filepath.

    Args:
        filepath (str): The filepath to export to.
        subdivision_level (int): The subdivision level to export.
            A value of zero will export the current subdivision level
            A negative value, e.g. -1 will go negatively from the highest
            subdivs - e.g. -1 is the highest available subdiv.

    """
    # TODO: If this overrides a tool's subdiv level it should actually revert
    #   it to the original level so that subsequent publishes behave the same
    filepath = filepath.replace("\\", "/")
    # Only set any subdiv level if subdiv level != 0
    set_subdivs_script = ""
    if subdivision_level != 0:
        set_subdivs_script = f"""
[VarSet, maxsubd, [IGetMax, "Tool:Geometry:SDiv"]]
[If, #maxsubd > 0,
    [ISet, "Tool:Geometry:SDiv", {subdivision_level}, 0],
    [ISet, "Tool:Geometry:SDiv", #maxsubd - {subdivision_level}, 0]
]"""

    # Export tool
    export_tool_zscript = f"""
[IFreeze, {set_subdivs_script}
[ISet, Preferences:ImportExport:Grp, 0]
[FileNameSetNext, "{filepath}"]
[IKeyPress, 13, [IPress, Tool:Export]]
]"""

    # We do not check for the export file's existence because Zbrush might
    # write the file in chunks, as such the file might exist before the writing
    # to it has finished
    execute_zscript_and_wait(export_tool_zscript)
    if not os.path.exists(filepath):
        raise RuntimeError(f"Export failed. File does not exist: {filepath}")


def is_in_edit_mode() -> bool:
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

    return bool(int(bool_mode))


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
