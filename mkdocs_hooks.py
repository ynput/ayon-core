import os
import sys
from pathlib import Path
from shutil import rmtree
import json

TMP_FILE = "./missing_init_files.json"


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
    nfiles = []

    for root in roots:
        if not os.path.exists(root):
            continue
        for dirpath, dirs, files in os.walk(root):
            if "__init__.py" in files:
                continue
            else:
                Path(f"{dirpath}/__init__.py").touch()
                nfiles.append(f"{dirpath}/__init__.py")
                sys.stdout.write(
                    "\r\x1b[K" + f"{msg}: created {len(nfiles)} "
                    "temp '__init__.py' files"
                )
                sys.stdout.flush()

    with open(TMP_FILE, "w") as f:
        json.dump(nfiles, f)

    sys.stdout.write("\n")
    sys.stdout.flush()


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
    with open(TMP_FILE, "r") as f:
        nfiles = json.load(f)

    for file in nfiles:
        Path(file).unlink()
        sys.stdout.write(
            "\r\x1b[K" + f"{msg}: removed {len(nfiles)} temp '__init__.py' files"
        )
        sys.stdout.flush()

    os.remove(TMP_FILE)

    sys.stdout.write("\n")
    sys.stdout.flush()


def remove_pychache_dirs(msg=""):
    """
    This function walks the current directory and removes all existing '__pycache__'
    directories.

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
            sys.stdout.write(
                "\r\x1b[K" + f"{msg}: removed {nremoved} '__pycache__' directories"
            )
            sys.stdout.flush()

    if not nremoved:
        sys.stdout.write(f"{msg}: no __pycache__ dirs found")

    sys.stdout.write("\n")
    sys.stdout.flush()


# mkdocs hooks -----------------------------------------------------------------


def on_startup(command, dirty):
    remove_pychache_dirs(msg="HOOK    -  on_startup")


def on_pre_build(config):
    """
    This function is called before the MkDocs build process begins. It adds
    temporary `__init__.py` files to directories that do not contain one, to
    make sure mkdocs doesn't ignore them.
    """
    add_missing_init_files(
        "client",
        "server",
        "services",
        "tests",
        msg="HOOK    -  on_pre_build",
    )


def on_post_build(config):
    """
    This function is called after the MkDocs build process ends. It removes
    temporary `__init__.py` files that were added in the `on_pre_build()`
    function.
    """
    remove_missing_init_files(msg="HOOK    -  on_post_build")
