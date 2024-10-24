"""
Temporary folder operations
"""

import os
import tempfile
from pathlib import Path
from ayon_core.lib import StringTemplate
from ayon_core.pipeline import Anatomy


def get_temp_dir(
    project_name, anatomy=None, prefix=None, suffix=None, use_local_temp=False
):
    """Get temporary dir path.

    If `use_local_temp` is set, tempdir will be created in local tempdir.
    If `anatomy` is not set, default anatomy will be used.
    If `prefix` or `suffix` is not set, default values will be used.

    It also supports `AYON_TMPDIR`, so studio can define own temp
    shared repository per project or even per more granular context.
    Template formatting is supported also with optional keys. Folder is
    created in case it doesn't exists.

    Args:
        project_name (str): Name of project.
        anatomy (Optional[Anatomy]): Project Anatomy object.
        suffix (Optional[str]): Suffix for tempdir.
        prefix (Optional[str]): Prefix for tempdir.
        use_local_temp (Optional[bool]): If True, temp dir will be created in
            local tempdir.

    Returns:
        str: Path to staging dir of instance.

    """
    prefix = prefix or "ay_tmp_"
    suffix = suffix or ""

    if use_local_temp:
        return _create_local_staging_dir(prefix, suffix)

    # make sure anatomy is set
    if not anatomy:
        anatomy = Anatomy(project_name)

    # get customized tempdir path from `OPENPYPE_TMPDIR` env var
    custom_temp_dir = _create_custom_tempdir(anatomy.project_name, anatomy)

    return _create_local_staging_dir(prefix, suffix, custom_temp_dir)


def _create_local_staging_dir(prefix, suffix, dirpath=None):
    """Create local staging dir

    Args:
        prefix (str): prefix for tempdir
        suffix (str): suffix for tempdir
        dirpath (Optional[str]): path to tempdir

    Returns:
        str: path to tempdir
    """
    # use pathlib for creating tempdir
    staging_dir = Path(tempfile.mkdtemp(
        prefix=prefix, suffix=suffix, dir=dirpath
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
    env_tmpdir = os.getenv(
        "AYON_TMPDIR",
    )
    if not env_tmpdir:
        return

    custom_tempdir = None
    if "{" in env_tmpdir:
        if anatomy is None:
            anatomy = Anatomy(project_name)
        # create base formate data
        template_data = {
            "root": anatomy.roots,
            "project": {
                "name": anatomy.project_name,
                "code": anatomy.project_code,
            },
        }
        # path is anatomy template
        custom_tempdir = StringTemplate.format_template(
            env_tmpdir, template_data)

        custom_tempdir_path = Path(custom_tempdir)

    else:
        # path is absolute
        custom_tempdir_path = Path(env_tmpdir)

    custom_tempdir_path.mkdir(parents=True, exist_ok=True)

    return custom_tempdir_path.as_posix()
