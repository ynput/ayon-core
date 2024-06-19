import io
import os
import sys
import re
import shutil
import argparse
import zipfile
import types
import importlib.machinery
import platform
import collections
from pathlib import Path
from typing import Optional, Iterable, Pattern, List, Tuple

# Patterns of directories to be skipped for server part of addon
IGNORE_DIR_PATTERNS: List[Pattern] = [
    re.compile(pattern)
    for pattern in {
        # Skip directories starting with '.'
        r"^\.",
        # Skip any pycache folders
        "^__pycache__$"
    }
]

# Patterns of files to be skipped for server part of addon
IGNORE_FILE_PATTERNS: List[Pattern] = [
    re.compile(pattern)
    for pattern in {
        # Skip files starting with '.'
        # NOTE this could be an issue in some cases
        r"^\.",
        # Skip '.pyc' files
        r"\.pyc$"
    }
]

IGNORED_HOSTS = [
    "flame",
    "harmony",
]

IGNORED_MODULES = []

PACKAGE_PY_TEMPLATE = """name = "{addon_name}"
version = "{addon_version}"
plugin_for = ["ayon_server"]
"""

CLIENT_VERSION_CONTENT = '''# -*- coding: utf-8 -*-
"""Package declaring AYON addon '{}' version."""
__version__ = "{}"
'''


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

        return super()._extract_member(member, tpath, pwd)


def _value_match_regexes(value: str, regexes: Iterable[Pattern]) -> bool:
    return any(
        regex.search(value)
        for regex in regexes
    )


def find_files_in_subdir(
    src_path: str,
    ignore_file_patterns: Optional[List[Pattern]] = None,
    ignore_dir_patterns: Optional[List[Pattern]] = None,
    include_empty_dirs: bool = True
):
    """Find all files to copy in subdirectories of given path.

    All files that match any of the patterns in 'ignore_file_patterns' will
        be skipped and any directories that match any of the patterns in
        'ignore_dir_patterns' will be skipped with all subfiles.

    Args:
        src_path (str): Path to directory to search in.
        ignore_file_patterns (Optional[List[Pattern]]): List of regexes
            to match files to ignore.
        ignore_dir_patterns (Optional[List[Pattern]]): List of regexes
            to match directories to ignore.
        include_empty_dirs (Optional[bool]): Do not skip empty directories.

    Returns:
        List[Tuple[str, str]]: List of tuples with path to file and parent
            directories relative to 'src_path'.
    """
    if not os.path.exists(src_path):
        return []

    if ignore_file_patterns is None:
        ignore_file_patterns = IGNORE_FILE_PATTERNS

    if ignore_dir_patterns is None:
        ignore_dir_patterns = IGNORE_DIR_PATTERNS
    output: List[Tuple[str, str]] = []

    hierarchy_queue = collections.deque()
    hierarchy_queue.append((src_path, []))
    while hierarchy_queue:
        item: Tuple[str, List[str]] = hierarchy_queue.popleft()
        dirpath, parents = item
        subnames = list(os.listdir(dirpath))
        if not subnames and include_empty_dirs:
            output.append((dirpath, os.path.sep.join(parents)))

        for name in subnames:
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


def create_addon_zip(
    output_dir: Path,
    addon_name: str,
    addon_version: str,
    files_mapping: List[Tuple[str, str]],
    client_zip_content: io.BytesIO
):
    zip_filepath = output_dir / f"{addon_name}-{addon_version}.zip"

    with ZipFileLongPaths(zip_filepath, "w", zipfile.ZIP_DEFLATED) as zipf:
        for src_path, dst_subpath in files_mapping:
            zipf.write(src_path, dst_subpath)

        if client_zip_content is not None:
            zipf.writestr("private/client.zip", client_zip_content.getvalue())


def prepare_client_zip(
    addon_dir: Path,
    addon_name: str,
    addon_version: str,
    client_dir: str
):
    if not client_dir:
        return None
    client_dir_obj = addon_dir / "client" / client_dir
    if not client_dir_obj.exists():
        return None

    # Update version.py with server version if 'version.py' is available
    version_path = client_dir_obj / "version.py"
    if version_path.exists():
        with open(version_path, "w") as stream:
            stream.write(
                CLIENT_VERSION_CONTENT.format(addon_name, addon_version)
            )

    zip_content = io.BytesIO()
    with ZipFileLongPaths(zip_content, "a", zipfile.ZIP_DEFLATED) as zipf:
        # Add client code content to zip
        for path, sub_path in find_files_in_subdir(
            str(client_dir_obj), include_empty_dirs=False
        ):
            sub_path = os.path.join(client_dir, sub_path)
            zipf.write(path, sub_path)

    zip_content.seek(0)
    return zip_content


def import_filepath(path: Path, module_name: Optional[str] = None):
    if not module_name:
        module_name = os.path.splitext(path.name)[0]

    # Convert to string
    path = str(path)
    module = types.ModuleType(module_name)
    module.__file__ = path

    # Use loader so module has full specs
    module_loader = importlib.machinery.SourceFileLoader(
        module_name, path
    )
    module_loader.exec_module(module)
    return module


def _get_server_mapping(
    addon_dir: Path, addon_version: str
) -> List[Tuple[str, str]]:
    server_dir = addon_dir / "server"
    public_dir = addon_dir / "public"
    src_package_py = addon_dir / "package.py"
    pyproject_toml = addon_dir / "client" / "pyproject.toml"

    mapping: List[Tuple[str, str]] = [
        (src_path, f"server/{sub_path}")
        for src_path, sub_path in find_files_in_subdir(str(server_dir))
    ]
    mapping.extend([
        (src_path, f"public/{sub_path}")
        for src_path, sub_path in find_files_in_subdir(str(public_dir))
    ])
    mapping.append((src_package_py.as_posix(), "package.py"))
    if pyproject_toml.exists():
        mapping.append((pyproject_toml.as_posix(), "private/pyproject.toml"))

    return mapping


def create_addon_package(
    addon_dir: Path,
    output_dir: Path,
    create_zip: bool,
):
    src_package_py = addon_dir / "package.py"

    package = import_filepath(src_package_py)
    addon_name = package.name
    addon_version = package.version

    files_mapping = _get_server_mapping(addon_dir, addon_version)

    client_dir = getattr(package, "client_dir", None)
    client_zip_content = prepare_client_zip(
        addon_dir, addon_name, addon_version, client_dir
    )

    if create_zip:
        create_addon_zip(
            output_dir,
            addon_name,
            addon_version,
            files_mapping,
            client_zip_content
        )

    else:
        addon_output_dir = output_dir / addon_dir.name / addon_version
        if addon_output_dir.exists():
            shutil.rmtree(str(addon_output_dir))

        addon_output_dir.mkdir(parents=True, exist_ok=True)

        for src_path, dst_subpath in files_mapping:
            dst_path = addon_output_dir / dst_subpath
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)

        if client_zip_content is not None:
            private_dir = addon_output_dir / "private"
            private_dir.mkdir(parents=True, exist_ok=True)
            with open(private_dir / "client.zip", "wb") as stream:
                stream.write(client_zip_content.read())


def main(
    output_dir=None,
    skip_zip=True,
    clear_output_dir=False,
    addons=None,
):
    current_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    create_zip = not skip_zip

    if output_dir:
        output_dir = Path(output_dir)
    else:
        output_dir = current_dir / "packages"

    if output_dir.exists() and clear_output_dir:
        shutil.rmtree(str(output_dir))

    print("Package creation started...")
    print(f"Output directory: {output_dir}")

    # Make sure output dir is created
    output_dir.mkdir(parents=True, exist_ok=True)
    ignored_addons = set(IGNORED_HOSTS) | set(IGNORED_MODULES)
    for addon_dir in current_dir.iterdir():
        if not addon_dir.is_dir():
            continue

        if addons and addon_dir.name not in addons:
            continue

        if addon_dir.name in ignored_addons:
            continue

        server_dir = addon_dir / "server"
        if not server_dir.exists():
            continue

        create_addon_package(addon_dir, output_dir, create_zip)

        print(f"- package '{addon_dir.name}' created")
    print(f"Package creation finished. Output directory: {output_dir}")


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
        "-o", "--output",
        dest="output_dir",
        default=None,
        help=(
            "Directory path where package will be created"
            " (Will be purged if already exists!)"
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
        "-a",
        "--addon",
        dest="addons",
        action="append",
        help="Limit addon creation to given addon name",
    )

    args = parser.parse_args(sys.argv[1:])
    if args.keep_sources:
        print("Keeping sources is not supported anymore!")

    main(
        args.output_dir,
        args.skip_zip,
        args.clear_output_dir,
        args.addons,
    )
