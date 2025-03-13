import os
import sys
from pathlib import Path
import json

TMP_FILE = "./missing_init_files.json"

def add_missing_init_files(*roots):
    nfiles = []

    for root in roots:
        for dirpath, dirs, files in os.walk(root):
            if "__init__.py" in files:
                continue
            else:
                Path(f"{dirpath}/__init__.py").touch()
                nfiles.append(f"{dirpath}/__init__.py")
                sys.stdout.write(
                    "\r\x1b[K" + f"PRE-BUILD: created {len(nfiles)} "
                    "temp __init__.py files"
                )
                sys.stdout.flush()

    with open(TMP_FILE, "w") as f:
        json.dump(nfiles, f)

    sys.stdout.write("\n")
    sys.stdout.flush()


def remove_missing_init_files():
    with open(TMP_FILE, "r") as f:
        nfiles = json.load(f)

    for file in nfiles:
        Path(file).unlink()
        sys.stdout.write(
            "\r\x1b[K" + f"POST_BUILD: removed {len(nfiles)} "
            "temp __init__.py files"
        )
        sys.stdout.flush()

    os.remove(TMP_FILE)

    sys.stdout.write("\n")
    sys.stdout.flush()


def on_pre_build(config):
    add_missing_init_files("client", "server", "tests")


def on_post_build(config):
    remove_missing_init_files()
