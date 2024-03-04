"""Prepares server package from addon repo to upload to server.

Requires Python 3.9. (Or at least 3.8+).

This script should be called from cloned addon repo.

It will produce 'package' subdirectory which could be pasted into server
addon directory directly (eg. into `ayon-backend/addons`).

Format of package folder:
ADDON_REPO/package/{addon name}/{addon version}

You can specify `--output_dir` in arguments to change output directory where
package will be created. Existing package directory will always be purged if
already present! This could be used to create package directly in server folder
if available.

Package contains server side files directly,
client side code zipped in `private` subfolder.
"""

import os
import sys
import re
import shutil
import argparse
import platform
import logging
import collections
import zipfile
import hashlib

from typing import Optional

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PACKAGE_PATH = os.path.join(CURRENT_DIR, "package.py")
package_content = {}
with open(PACKAGE_PATH, "r") as stream:
    exec(stream.read(), package_content)

ADDON_VERSION = package_content["version"]
ADDON_NAME = package_content["name"]
ADDON_CLIENT_DIR = package_content["client_dir"]
CLIENT_VERSION_CONTENT = '''# -*- coding: utf-8 -*-
"""Package declaring AYON core addon version."""
__version__ = "{}"
'''

# Patterns of directories to be skipped for server part of addon
IGNORE_DIR_PATTERNS = [
    re.compile(pattern)
    for pattern in {
        # Skip directories starting with '.'
        r"^\.",
        # Skip any pycache folders
        "^__pycache__$"
    }
]

# Patterns of files to be skipped for server part of addon
IGNORE_FILE_PATTERNS = [
    re.compile(pattern)
    for pattern in {
        # Skip files starting with '.'
        # NOTE this could be an issue in some cases
        r"^\.",
        # Skip '.pyc' files
        r"\.pyc$"
    }
]


def calculate_file_checksum(filepath, hash_algorithm, chunk_size=10000):
    func = getattr(hashlib, hash_algorithm)
    hash_obj = func()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            hash_obj.update(chunk)
    return hash_obj.hexdigest()


class ZipFileLongPaths(zipfile.ZipFile):
    """Allows longer paths in zip files.

    Regular DOS paths are limited to MAX_PATH (260) characters, including
    the string's terminating NUL character.
    That limit can be exceeded by using an extended-length path that
    starts with the '\\?\' prefix.
    """
    _is_windows = platform.system().lower() == "windows"

    def _extract_member(self, member, tpath, pwd):
        if self._is_windows:
            tpath = os.path.abspath(tpath)
            if tpath.startswith("\\\\"):
                tpath = "\\\\?\\UNC\\" + tpath[2:]
            else:
                tpath = "\\\\?\\" + tpath

        return super(ZipFileLongPaths, self)._extract_member(
            member, tpath, pwd
        )


def safe_copy_file(src_path, dst_path):
    """Copy file and make sure destination directory exists.

    Ignore if destination already contains directories from source.

    Args:
        src_path (str): File path that will be copied.
        dst_path (str): Path to destination file.
    """

    if src_path == dst_path:
        return

    dst_dir = os.path.dirname(dst_path)
    try:
        os.makedirs(dst_dir)
    except Exception:
        pass

    shutil.copy2(src_path, dst_path)


def _value_match_regexes(value, regexes):
    for regex in regexes:
        if regex.search(value):
            return True
    return False


def find_files_in_subdir(
    src_path,
    ignore_file_patterns=None,
    ignore_dir_patterns=None
):
    if ignore_file_patterns is None:
        ignore_file_patterns = IGNORE_FILE_PATTERNS

    if ignore_dir_patterns is None:
        ignore_dir_patterns = IGNORE_DIR_PATTERNS
    output = []

    hierarchy_queue = collections.deque()
    hierarchy_queue.append((src_path, []))
    while hierarchy_queue:
        item = hierarchy_queue.popleft()
        dirpath, parents = item
        for name in os.listdir(dirpath):
            path = os.path.join(dirpath, name)
            if os.path.isfile(path):
                if not _value_match_regexes(name, ignore_file_patterns):
                    items = list(parents)
                    items.append(name)
                    output.append((path, os.path.sep.join(items)))
                continue

            if not _value_match_regexes(name, ignore_dir_patterns):
                items = list(parents)
                items.append(name)
                hierarchy_queue.append((path, items))

    return output


def copy_server_content(addon_output_dir, current_dir, log):
    """Copies server side folders to 'addon_package_dir'

    Args:
        addon_output_dir (str): package dir in addon repo dir
        current_dir (str): addon repo dir
        log (logging.Logger)
    """

    log.info("Copying server content")

    filepaths_to_copy = []
    server_dirpath = os.path.join(current_dir, "server")

    for item in find_files_in_subdir(server_dirpath):
        src_path, dst_subpath = item
        dst_path = os.path.join(addon_output_dir, "server", dst_subpath)
        filepaths_to_copy.append((src_path, dst_path))

    # Copy files
    for src_path, dst_path in filepaths_to_copy:
        safe_copy_file(src_path, dst_path)


def _update_client_version(client_addon_dir):
    """Write version.py file to 'client' directory.

    Make sure the version in client dir is the same as in package.py.

    Args:
        client_addon_dir (str): Directory path of client addon.
    """

    dst_version_path = os.path.join(client_addon_dir, "version.py")
    with open(dst_version_path, "w") as stream:
        stream.write(CLIENT_VERSION_CONTENT.format(ADDON_VERSION))


def zip_client_side(addon_package_dir, current_dir, log):
    """Copy and zip `client` content into 'addon_package_dir'.

    Args:
        addon_package_dir (str): Output package directory path.
        current_dir (str): Directory path of addon source.
        log (logging.Logger): Logger object.
    """

    client_dir = os.path.join(current_dir, "client")
    client_addon_dir = os.path.join(client_dir, ADDON_CLIENT_DIR)
    if not os.path.isdir(client_addon_dir):
        raise ValueError(
            f"Failed to find client directory '{client_addon_dir}'"
        )

    log.info("Preparing client code zip")
    private_dir = os.path.join(addon_package_dir, "private")

    if not os.path.exists(private_dir):
        os.makedirs(private_dir)

    _update_client_version(client_addon_dir)

    zip_filepath = os.path.join(os.path.join(private_dir, "client.zip"))
    with ZipFileLongPaths(zip_filepath, "w", zipfile.ZIP_DEFLATED) as zipf:
        # Add client code content to zip
        for path, sub_path in find_files_in_subdir(client_addon_dir):
            sub_path = os.path.join(ADDON_CLIENT_DIR, sub_path)
            zipf.write(path, sub_path)

    shutil.copy(os.path.join(client_dir, "pyproject.toml"), private_dir)


def create_server_package(
    output_dir: str,
    addon_output_dir: str,
    log: logging.Logger
):
    """Create server package zip file.

    The zip file can be installed to a server using UI or rest api endpoints.

    Args:
        output_dir (str): Directory path to output zip file.
        addon_output_dir (str): Directory path to addon output directory.
        log (logging.Logger): Logger object.
    """

    log.info("Creating server package")
    output_path = os.path.join(
        output_dir, f"{ADDON_NAME}-{ADDON_VERSION}.zip"
    )
    with ZipFileLongPaths(output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        # Move addon content to zip into 'addon' directory
        addon_output_dir_offset = len(addon_output_dir) + 1
        for root, _, filenames in os.walk(addon_output_dir):
            if not filenames:
                continue

            dst_root = None
            if root != addon_output_dir:
                dst_root = root[addon_output_dir_offset:]
            for filename in filenames:
                src_path = os.path.join(root, filename)
                dst_path = filename
                if dst_root:
                    dst_path = os.path.join(dst_root, dst_path)
                zipf.write(src_path, dst_path)

    log.info(f"Output package can be found: {output_path}")


def main(
    output_dir: Optional[str]=None,
    skip_zip: bool=False,
    keep_sources: bool=False,
    clear_output_dir: bool=False
):
    log = logging.getLogger("create_package")
    log.info("Start creating package")

    current_dir = os.path.dirname(os.path.abspath(__file__))
    if not output_dir:
        output_dir = os.path.join(current_dir, "package")


    new_created_version_dir = os.path.join(
        output_dir, ADDON_NAME, ADDON_VERSION
    )

    if os.path.isdir(new_created_version_dir) and clear_output_dir:
        log.info(f"Purging {new_created_version_dir}")
        shutil.rmtree(output_dir)

    log.info(f"Preparing package for {ADDON_NAME}-{ADDON_VERSION}")

    addon_output_root = os.path.join(output_dir, ADDON_NAME)
    addon_output_dir = os.path.join(addon_output_root, ADDON_VERSION)
    if not os.path.exists(addon_output_dir):
        os.makedirs(addon_output_dir)

    copy_server_content(addon_output_dir, current_dir, log)
    safe_copy_file(
        PACKAGE_PATH,
        os.path.join(addon_output_dir, os.path.basename(PACKAGE_PATH))
    )
    zip_client_side(addon_output_dir, current_dir, log)

    # Skip server zipping
    if not skip_zip:
        create_server_package(output_dir, addon_output_dir, log)
        # Remove sources only if zip file is created
        if not keep_sources:
            log.info("Removing source files for server package")
            shutil.rmtree(addon_output_root)
    log.info("Package creation finished")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-zip",
        dest="skip_zip",
        action="store_true",
        help=(
            "Skip zipping server package and create only"
            " server folder structure."
        )
    )
    parser.add_argument(
        "--keep-sources",
        dest="keep_sources",
        action="store_true",
        help=(
            "Keep folder structure when server package is created."
        )
    )
    parser.add_argument(
        "-c", "--clear-output-dir",
        dest="clear_output_dir",
        action="store_true",
        help=(
            "Clear output directory before package creation."
        )
    )

    parser.add_argument(
        "-o", "--output",
        dest="output_dir",
        default=None,
        help=(
            "Directory path where package will be created"
            " (Will be purged if already exists!)"
        )
    )

    args = parser.parse_args(sys.argv[1:])
    main(
        args.output_dir,
        args.skip_zip,
        args.keep_sources,
        args.clear_output_dir
    )
