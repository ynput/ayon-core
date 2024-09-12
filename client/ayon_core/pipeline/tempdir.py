"""
Temporary folder operations
"""

import os
import tempfile
from pathlib import Path
from ayon_core.lib import StringTemplate
from ayon_core.pipeline import Anatomy


def get_temp_dir(
    project_name=None, anatomy=None, prefix=None, suffix=None, make_local=False
):
    """Get temporary dir path.

    If `make_local` is set, tempdir will be created in local tempdir.
    If `anatomy` is not set, default anatomy will be used.
    If `prefix` or `suffix` is not set, default values will be used.

    It also supports `OPENPYPE_TMPDIR`, so studio can define own temp
    shared repository per project or even per more granular context.
    Template formatting is supported also with optional keys. Folder is
    created in case it doesn't exists.

    Available anatomy formatting keys:
        - root[work | <root name key>]
        - project[name | code]

    Note:
        Staging dir does not have to be necessarily in tempdir so be careful
        about its usage.

    Args:
        project_name (str)[optional]: Name of project.
        anatomy (openpype.pipeline.Anatomy)[optional]: Anatomy object.
        make_local (bool)[optional]: If True, temp dir will be created in
            local tempdir.
        suffix (str)[optional]: Suffix for tempdir.
        prefix (str)[optional]: Prefix for tempdir.

    Returns:
        str: Path to staging dir of instance.
    """
    prefix = prefix or "ay_tmp_"
    suffix = suffix or ""

    if make_local:
        return _create_local_staging_dir(prefix, suffix)

    # make sure anatomy is set
    if not anatomy:
        anatomy = Anatomy(project_name)

    # get customized tempdir path from `OPENPYPE_TMPDIR` env var
    custom_temp_dir = _create_custom_tempdir(anatomy.project_name, anatomy)

    return _create_local_staging_dir(prefix, suffix, custom_temp_dir)


def _create_local_staging_dir(prefix, suffix, dir=None):
    """Create local staging dir

    Args:
        prefix (str): prefix for tempdir
        suffix (str): suffix for tempdir

    Returns:
        str: path to tempdir
    """
    # use pathlib for creating tempdir
    staging_dir = Path(tempfile.mkdtemp(
        prefix=prefix, suffix=suffix, dir=dir
    ))

    return staging_dir.as_posix()


def _create_custom_tempdir(project_name, anatomy=None):
    """ Create custom tempdir

    Template path formatting is supporting:
    - optional key formatting
    - available keys:
        - root[work | <root name key>]
        - project[name | code]

    Args:
        project_name (str): project name
        anatomy (ayon_core.pipeline.Anatomy)[optional]: Anatomy object

    Returns:
        str | None: formatted path or None
    """
    env_tmpdir = os.getenv("AYON_TMPDIR")
    if not env_tmpdir:
        env_tmpdir = os.getenv("OPENPYPE_TMPDIR")
        if not env_tmpdir:
            return
        print(
            "DEPRECATION WARNING: Used 'OPENPYPE_TMPDIR' environment"
            " variable. Please use 'AYON_TMPDIR' instead."
        )

    custom_tempdir = None
    if "{" in env_tmpdir:
        if anatomy is None:
            anatomy = Anatomy(project_name)
        # create base formate data
        template_formatting_data = {
            "root": anatomy.roots,
            "project": {
                "name": anatomy.project_name,
                "code": anatomy.project_code,
            }
        }
        # path is anatomy template
        custom_tempdir = StringTemplate.format_template(
            env_tmpdir, template_formatting_data)

        custom_tempdir_path = Path(custom_tempdir)

    else:
        # path is absolute
        custom_tempdir_path = Path(env_tmpdir)

    custom_tempdir_path.mkdir(parents=True, exist_ok=True)

    return custom_tempdir_path.as_posix()
