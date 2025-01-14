import os
import sys
import subprocess
import platform
import json
import tempfile

from .log import Logger
from .vendor_bin_utils import find_executable

# MSDN process creation flag (Windows only)
CREATE_NO_WINDOW = 0x08000000


def execute(args, silent=False, cwd=None, env=None, shell=None):
    """Execute command as process.

    This will execute given command as process, monitor its output
    and log it appropriately.

    .. seealso::

        :mod:`subprocess` module in Python.

    Args:
        args (list): list of arguments passed to process.
        silent (bool): control output of executed process.
        cwd (str): current working directory for process.
        env (dict): environment variables for process.
        shell (bool): use shell to execute, default is no.

    Returns:
        int: return code of process

    """
    log_levels = ["DEBUG:", "INFO:", "ERROR:", "WARNING:", "CRITICAL:"]

    log = Logger.get_logger("execute")
    log.info("Executing ({})".format(" ".join(args)))
    popen = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1,
        cwd=cwd,
        env=env or os.environ,
        shell=shell
    )

    # Blocks until finished
    while True:
        line = popen.stdout.readline()
        if line == "":
            break
        if silent:
            continue
        line_test = False
        for test_string in log_levels:
            if line.startswith(test_string):
                line_test = True
                break
        if not line_test:
            print(line[:-1])

    log.info("Execution is finishing up ...")

    popen.wait()
    return popen.returncode


def run_subprocess(*args, **kwargs):
    """Convenience method for getting output errors for subprocess.

    Output logged when process finish.

    Entered arguments and keyword arguments are passed to subprocess Popen.

    On windows are 'creationflags' filled with flags that should cause ignore
    creation of new window.

    Args:
        *args: Variable length argument list passed to Popen.
        **kwargs : Arbitrary keyword arguments passed to Popen. Is possible to
            pass `logging.Logger` object under "logger" to use custom logger
            for output.

    Returns:
        str: Full output of subprocess concatenated stdout and stderr.

    Raises:
        RuntimeError: Exception is raised if process finished with nonzero
            return code.

    """
    # Modify creation flags on windows to hide console window if in UI mode
    if (
        platform.system().lower() == "windows"
        and "creationflags" not in kwargs
        # shell=True already tries to hide the console window
        # and passing these creationflags then shows the window again
        # so we avoid it for shell=True cases
        and kwargs.get("shell") is not True
    ):
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            | getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )

    # Escape parentheses for bash
    if (
        kwargs.get("shell") is True
        and len(args) == 1
        and isinstance(args[0], str)
        and os.getenv("SHELL") in ("/bin/bash", "/bin/sh")
    ):
        new_arg = (
            args[0]
            .replace("(", "\\(")
            .replace(")", "\\)")
        )
        args = (new_arg, )

    # Get environents from kwarg or use current process environments if were
    # not passed.
    env = kwargs.get("env") or os.environ
    # Make sure environment contains only strings
    filtered_env = {str(k): str(v) for k, v in env.items()}

    # Use lib's logger if was not passed with kwargs.
    logger = kwargs.pop("logger", None)
    if logger is None:
        logger = Logger.get_logger("run_subprocess")

    # set overrides
    kwargs["stdout"] = kwargs.get("stdout", subprocess.PIPE)
    kwargs["stderr"] = kwargs.get("stderr", subprocess.PIPE)
    kwargs["stdin"] = kwargs.get("stdin", subprocess.PIPE)
    kwargs["env"] = filtered_env

    proc = subprocess.Popen(*args, **kwargs)

    full_output = ""
    _stdout, _stderr = proc.communicate()
    if _stdout:
        _stdout = _stdout.decode("utf-8", errors="backslashreplace")
        full_output += _stdout
        logger.debug(_stdout)

    if _stderr:
        _stderr = _stderr.decode("utf-8", errors="backslashreplace")
        # Add additional line break if output already contains stdout
        if full_output:
            full_output += "\n"
        full_output += _stderr
        logger.info(_stderr)

    if proc.returncode != 0:
        exc_msg = "Executing arguments was not successful: \"{}\"".format(args)
        if _stdout:
            exc_msg += "\n\nOutput:\n{}".format(_stdout)

        if _stderr:
            exc_msg += "Error:\n{}".format(_stderr)

        raise RuntimeError(exc_msg)

    return full_output


def clean_envs_for_ayon_process(env=None):
    """Modify environments that may affect ayon-launcher process.

    Main reason to implement this function is to pop PYTHONPATH which may be
    affected by in-host environments.

    Args:
        env (Optional[dict[str, str]]): Environment variables to modify.

    Returns:
        dict[str, str]: Environment variables for ayon process.

    """
    if env is None:
        env = os.environ

    # Exclude some environment variables from a copy of the environment
    env = env.copy()
    for key in ["PYTHONPATH", "PYTHONHOME"]:
        env.pop(key, None)

    return env


def run_ayon_launcher_process(*args, add_sys_paths=False, **kwargs):
    """Execute AYON process with passed arguments and wait.

    Wrapper for 'run_process' which prepends AYON executable arguments
    before passed arguments and define environments if are not passed.

    Values from 'os.environ' are used for environments if are not passed.
    They are cleaned using 'clean_envs_for_ayon_process' function.

    Example:
    ```
    run_ayon_process("run", "<path to .py script>")
    ```

    Args:
        *args (str): ayon-launcher cli arguments.
        **kwargs (Any): Keyword arguments for subprocess.Popen.

    Returns:
        str: Full output of subprocess concatenated stdout and stderr.

    """
    args = get_ayon_launcher_args(*args)
    env = kwargs.pop("env", None)
    # Keep env untouched if are passed and not empty
    if not env:
        # Skip envs that can affect AYON launcher process
        # - fill more if you find more
        env = clean_envs_for_ayon_process(os.environ)

    if add_sys_paths:
        new_pythonpath = list(sys.path)
        lookup_set = set(new_pythonpath)
        for path in (env.get("PYTHONPATH") or "").split(os.pathsep):
            if path and path not in lookup_set:
                new_pythonpath.append(path)
                lookup_set.add(path)
        env["PYTHONPATH"] = os.pathsep.join(new_pythonpath)

    return run_subprocess(args, env=env, **kwargs)


def run_detached_process(args, **kwargs):
    """Execute process with passed arguments as separated process.

    Example:
        >>> run_detached_process("run", "./path_to.py")


    Args:
        args (Iterable[str]): AYON cli arguments.
        **kwargs (dict): Keyword arguments for subprocess.Popen.

    Returns:
        subprocess.Popen: Pointer to launched process but it is possible that
            launched process is already killed (on linux).

    """
    env = kwargs.pop("env", None)
    # Keep env untouched if are passed and not empty
    if not env:
        env = os.environ

    # Create copy of passed env
    kwargs["env"] = {k: v for k, v in env.items()}

    low_platform = platform.system().lower()
    if low_platform == "darwin":
        new_args = ["open", "-na", args.pop(0), "--args"]
        new_args.extend(args)
        args = new_args

    elif low_platform == "windows":
        flags = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
        )
        kwargs["creationflags"] = flags

        if not sys.stdout:
            kwargs["stdout"] = subprocess.DEVNULL
            kwargs["stderr"] = subprocess.DEVNULL

    elif low_platform == "linux" and get_linux_launcher_args() is not None:
        json_data = {
            "args": args,
            "env": kwargs.pop("env")
        }
        json_temp = tempfile.NamedTemporaryFile(
            mode="w", prefix="op_app_args", suffix=".json", delete=False
        )
        json_temp.close()
        json_temp_filpath = json_temp.name
        with open(json_temp_filpath, "w") as stream:
            json.dump(json_data, stream)

        new_args = get_linux_launcher_args()
        new_args.append(json_temp_filpath)

        # Create mid-process which will launch application
        process = subprocess.Popen(new_args, **kwargs)
        # Wait until the process finishes
        #   - This is important! The process would stay in "open" state.
        process.wait()
        # Remove the temp file
        os.remove(json_temp_filpath)
        # Return process which is already terminated
        return process

    process = subprocess.Popen(args, **kwargs)
    return process


def path_to_subprocess_arg(path):
    """Prepare path for subprocess arguments.

    Returned path can be wrapped with quotes or kept as is.

    Args:
        path (str): Path to be converted.

    Returns:
        str: Converted path.
    """
    return subprocess.list2cmdline([path])


def get_ayon_launcher_args(*args):
    """Arguments to run AYON launcher process.

    Arguments for subprocess when need to spawn new AYON launcher process.

    Reasons:
        AYON launcher started from code has different executable set to
            virtual env python and must have path to script as first argument
            which is not needed for built application.

    Args:
        *args (str): Any arguments that will be added after executables.

    Returns:
        list[str]: List of arguments to run AYON launcher process.

    """
    executable = os.environ["AYON_EXECUTABLE"]
    launch_args = [executable]

    executable_filename = os.path.basename(executable)
    if "python" in executable_filename.lower():
        filepath = os.path.join(os.environ["AYON_ROOT"], "start.py")
        launch_args.append(filepath)

    if args:
        launch_args.extend(args)

    return launch_args


def get_linux_launcher_args(*args):
    """Path to application mid process executable.

    This function should be able as arguments are different when used
    from code and build.

    It is possible that this function is used in AYON build which does
    not have yet the new executable. In that case 'None' is returned.

    Todos:
        Replace by script in scripts for ayon-launcher.

    Args:
        args (iterable): List of additional arguments added after executable
            argument.

    Returns:
        list: Executables with possible positional argument to script when
            called from code.
    """
    filename = "app_launcher"
    executable = os.environ["AYON_EXECUTABLE"]

    executable_filename = os.path.basename(executable)
    if "python" in executable_filename.lower():
        root = os.environ["AYON_ROOT"]
        script_path = os.path.join(root, "{}.py".format(filename))
        launch_args = [executable, script_path]
    else:
        new_executable = os.path.join(
            os.path.dirname(executable),
            filename
        )
        executable_path = find_executable(new_executable)
        if executable_path is None:
            return None
        launch_args = [executable_path]

    if args:
        launch_args.extend(args)

    return launch_args
