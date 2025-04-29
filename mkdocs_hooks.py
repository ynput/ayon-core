import os
from pathlib import Path
from shutil import rmtree
import json
import glob
import logging

TMP_FILE = "./missing_init_files.json"
NFILES = []

# -----------------------------------------------------------------------------


class ColorFormatter(logging.Formatter):
    grey = "\x1b[38;20m"
    green = "\x1b[32;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    fmt = (
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s "  # noqa
        "(%(filename)s:%(lineno)d)"
    )

    FORMATS = {
        logging.DEBUG: grey + fmt + reset,
        logging.INFO: green + fmt + reset,
        logging.WARNING: yellow + fmt + reset,
        logging.ERROR: red + fmt + reset,
        logging.CRITICAL: bold_red + fmt + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


ch = logging.StreamHandler()
ch.setFormatter(ColorFormatter())

logging.basicConfig(
    level=logging.INFO,
    handlers=[ch],
)


# -----------------------------------------------------------------------------


def create_init_file(dirpath, msg):
    global NFILES
    ini_file = f"{dirpath}/__init__.py"
    Path(ini_file).touch()
    NFILES.append(ini_file)
    logging.info(f"{msg}: created '{ini_file}'")


def create_parent_init_files(dirpath: str, rootpath: str, msg: str):
    parent_path = dirpath
    while parent_path != rootpath:
        parent_path = os.path.dirname(parent_path)
        parent_init = os.path.join(parent_path, "__init__.py")
        if not os.path.exists(parent_init):
            create_init_file(parent_path, msg)
        else:
            break


def add_missing_init_files(*roots, msg=""):
    """
    This function takes in one or more root directories as arguments and scans
    them for Python files without an `__init__.py` file. It generates a JSON
    file named `missing_init_files.json` containing the paths of these files.

    Args:
        *roots: Variable number of root directories to scan.

    Returns:
        None
    """

    for root in roots:
        if not os.path.exists(root):
            continue
        rootpath = os.path.abspath(root)
        for dirpath, dirs, files in os.walk(rootpath):
            if "__init__.py" in files:
                continue

            if "." in dirpath:
                continue

            if not glob.glob(os.path.join(dirpath, "*.py")):
                continue

            create_init_file(dirpath, msg)
            create_parent_init_files(dirpath, rootpath, msg)

    with open(TMP_FILE, "w") as f:
        json.dump(NFILES, f)


def remove_missing_init_files(msg=""):
    """
    This function removes temporary `__init__.py` files created in the
    `add_missing_init_files()` function. It reads the paths of these files from
    a JSON file named `missing_init_files.json`.

    Args:
        None

    Returns:
        None
    """
    global NFILES
    nfiles = []
    if os.path.exists(TMP_FILE):
        with open(TMP_FILE, "r") as f:
            nfiles = json.load(f)
    else:
        nfiles = NFILES

    for file in nfiles:
        Path(file).unlink()
        logging.info(f"{msg}: removed {file}")

    os.remove(TMP_FILE)
    NFILES = []


def remove_pychache_dirs(msg=""):
    """
    This function walks the current directory and removes all existing
    '__pycache__' directories.

    Args:
        msg: An optional message to display during the removal process.

    Returns:
        None
    """
    nremoved = 0

    for dirpath, dirs, files in os.walk("."):
        if "__pycache__" in dirs:
            pydir = Path(f"{dirpath}/__pycache__")
            rmtree(pydir)
            nremoved += 1
            logging.info(f"{msg}: removed '{pydir}'")

    if not nremoved:
        logging.info(f"{msg}: no __pycache__ dirs found")


# mkdocs hooks ----------------------------------------------------------------


def on_startup(command, dirty):
    remove_pychache_dirs(msg="HOOK    -  on_startup")


def on_pre_build(config):
    """
    This function is called before the MkDocs build process begins. It adds
    temporary `__init__.py` files to directories that do not contain one, to
    make sure mkdocs doesn't ignore them.
    """
    try:
        add_missing_init_files(
            "client",
            "server",
            "services",
            msg="HOOK    -  on_pre_build",
        )
    except BaseException as e:
        logging.error(e)
        remove_missing_init_files(
            msg="HOOK    -  on_post_build: cleaning up on error !"
        )
        raise


def on_post_build(config):
    """
    This function is called after the MkDocs build process ends. It removes
    temporary `__init__.py` files that were added in the `on_pre_build()`
    function.
    """
    remove_missing_init_files(msg="HOOK    -  on_post_build")
