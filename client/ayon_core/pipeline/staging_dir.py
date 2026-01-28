from __future__ import annotations

import logging
import warnings
import functools
from typing import Optional, Any
from dataclasses import dataclass

from ayon_core.lib import Logger, filter_profiles
from ayon_core.settings import get_project_settings

from .template_data import get_template_data
from .anatomy import Anatomy
from .tempdir import get_temp_dir

log = Logger.get_logger(__name__)


@dataclass
class StagingDir:
    directory: str
    is_persistent: bool
    # Whether the staging dir is a custom staging dir
    is_custom: bool

    def __setattr__(self, key, value):
        if key == "persistent":
            msg = (
                "'StagingDir.persistent' is deprecated."
                " Use 'StagingDir.is_persistent' instead."
            )
            log.warning(msg)
            warnings.warn(msg, DeprecationWarning, stacklevel=2)
            key = "is_persistent"
        super().__setattr__(key, value)

    @property
    def persistent(self):
        msg = (
            "'StagingDir.persistent' is deprecated."
            " Use 'StagingDir.is_persistent' instead."
        )
        log.warning(msg)
        warnings.warn(msg, DeprecationWarning, stacklevel=2)
        return self.is_persistent


def _get_staging_dir_config_wrap(func):
    """Change 'product_type' kwarg to 'product_base_type' compatibility."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if "product_type" in kwargs:
            msg = (
                "Found 'product_type' kwarg in 'get_staging_dir_config',"
                " use 'product_base_type' instead."
            )
            log.warning(msg)
            warnings.warn(msg, DeprecationWarning, stacklevel=2)

            kwargs["product_base_type"] = kwargs.pop("product_type")

        if len(args) > 6:
            msg = (
                "Got more positional arguments for 'get_staging_dir_config'"
                " than expected. Please use explicit kwargs instead."
            )
            log.warning(msg)
            warnings.warn(msg, DeprecationWarning, stacklevel=2)
            args, rem = args[:6], args[6:]
            for kwarg in ("project_settings", "anatomy", "log"):
                if not rem:
                    break
                kwargs[kwarg] = rem.pop(0)

        return func(*args, **kwargs)
    return wrapper


@_get_staging_dir_config_wrap
def get_staging_dir_config(
    project_name: str,
    task_type: Optional[str],
    task_name: Optional[str],
    product_base_type: str,
    product_name: str,
    host_name: str,
    *,
    project_settings: Optional[dict[str, Any]] = None,
    anatomy: Optional[Anatomy] = None,
    log: Optional[logging.Logger] = None,
) -> Optional[dict[str, Any]]:
    """Get matching staging dir profile.

    Args:
        host_name (str): Name of host.
        project_name (str): Name of project.
        task_type (Optional[str]): Type of task.
        task_name (Optional[str]): Name of task.
        product_base_type (str): Product base type.
        product_name (str): Name of product.
        project_settings(dict[str, Any]): Prepared project settings.
        anatomy (dict[str, Any])
        log (Optional[logging.Logger])

    Returns:
        dict or None: Data with directory template and is_persistent or None

    Raises:
        KeyError - if misconfigured template should be used

    """
    settings = project_settings or get_project_settings(project_name)

    staging_dir_profiles = settings["core"]["tools"]["publish"][
        "custom_staging_dir_profiles"
    ]

    if not staging_dir_profiles:
        return None

    if not log:
        log = Logger.get_logger("get_staging_dir_config")

    filtering_criteria = {
        "host_names": host_name,
        "task_types": task_type,
        "task_names": task_name,
        "product_base_types": product_base_type,
        "product_names": product_name,
    }
    profile = filter_profiles(
        staging_dir_profiles, filtering_criteria, logger=log)

    if not profile or not profile["active"]:
        return None

    if not anatomy:
        anatomy = Anatomy(project_name)

    # get template from template name
    template_name = profile["template_name"]

    template = anatomy.get_template_item("staging", template_name)

    if not template:
        # template should always be found either from anatomy or from profile
        raise KeyError(
            f"Staging template '{template_name}' was not found."
            "Check project anatomy or settings at: "
            "'ayon+settings://core/tools/publish/custom_staging_dir_profiles'"
        )

    data_persistence = profile["custom_staging_dir_persistent"]

    return {"template": template, "persistence": data_persistence}


def _get_staging_dir_info_wrap(func):
    """Change 'product_type' kwarg to 'product_base_type' compatibility."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if "product_type" in kwargs:
            msg = (
                "Found 'product_type' kwarg in 'get_staging_dir_info',"
                " use 'product_base_type' instead."
            )
            log.warning(msg)
            warnings.warn(msg, DeprecationWarning, stacklevel=2)

            kwargs["product_base_type"] = kwargs.pop("product_type")

        if len(args) > 7:
            msg = (
                "Got more positional arguments for 'get_staging_dir_info'"
                " than expected. Please use explicit kwargs instead."
            )
            log.warning(msg)
            warnings.warn(msg, DeprecationWarning, stacklevel=2)
            args, rem = args[:6], args[6:]
            for kwarg in (
                "anatomy",
                "project_settings",
                "template_data",
                "always_return_path",
                "force_tmp_dir",
                "logger",
                "prefix",
                "suffix",
                "username",
            ):
                if not rem:
                    break
                kwargs[kwarg] = rem.pop(0)

        return func(*args, **kwargs)
    return wrapper


def get_staging_dir_info(
    project_entity: dict[str, Any],
    folder_entity: Optional[dict[str, Any]],
    task_entity: Optional[dict[str, Any]],
    product_base_type: str,
    product_name: str,
    host_name: str,
    *,
    anatomy: Optional[Anatomy] = None,
    project_settings: Optional[dict[str, Any]] = None,
    template_data: Optional[dict[str, Any]] = None,
    always_return_path: bool = True,
    force_tmp_dir: bool = False,
    logger: Optional[logging.Logger] = None,
    prefix: Optional[str] = None,
    suffix: Optional[str] = None,
    username: Optional[str] = None,
) -> Optional[StagingDir]:
    """Get staging dir info data.

    If `force_temp` is set, staging dir will be created as tempdir.
    If `always_get_some_dir` is set, staging dir will be created as tempdir if
    no staging dir profile is found.
    If `prefix` or `suffix` is not set, default values will be used.

    Arguments:
        project_entity (dict[str, Any]): Project entity.
        folder_entity (Optional[dict[str, Any]]): Folder entity.
        task_entity (Optional[dict[str, Any]]): Task entity.
        product_base_type (str): Type of product.
        product_name (str): Name of product.
        host_name (str): Name of host.
        anatomy (Optional[Anatomy]): Anatomy object.
        project_settings (Optional[dict[str, Any]]): Prepared project settings.
        template_data (Optional[dict[str, Any]]): Additional data for
            formatting staging dir template.
        always_return_path (Optional[bool]): If True, staging dir will be
            created as tempdir if no staging dir profile is found. Input value
            False will return None if no staging dir profile is found.
        force_tmp_dir (Optional[bool]): If True, staging dir will be created as
            tempdir.
        logger (Optional[logging.Logger]): Logger instance.
        prefix (Optional[str]) Optional prefix for staging dir name.
        suffix (Optional[str]): Optional suffix for staging dir name.
        username (Optional[str]): AYON Username.

    Returns:
        Optional[StagingDir]: Staging dir info data

    """
    log = logger or Logger.get_logger("get_staging_dir_info")

    if anatomy is None:
        anatomy = Anatomy(
            project_entity["name"], project_entity=project_entity
        )

    if force_tmp_dir:
        return StagingDir(
            get_temp_dir(
                project_name=project_entity["name"],
                anatomy=anatomy,
                prefix=prefix,
                suffix=suffix,
            ),
            is_persistent=False,
            is_custom=False
        )

    # making few queries to database
    ctx_data = get_template_data(
        project_entity,
        folder_entity,
        task_entity,
        host_name,
        settings=project_settings,
        username=username
    )

    # add additional data
    ctx_data["product"] = {
        "basetype": product_base_type,
        "name": product_name,
        # This might be confusing as product type is not passed
        #   to the function
        "type": product_base_type,
    }

    # add additional template formatting data
    if template_data:
        ctx_data.update(template_data)

    task_name = task_type = None
    if task_entity:
        task_name = task_entity["name"]
        task_type = task_entity["taskType"]

    # get staging dir config
    staging_dir_config = get_staging_dir_config(
        project_entity["name"],
        task_type,
        task_name,
        product_base_type,
        product_name,
        host_name,
        project_settings=project_settings,
        anatomy=anatomy,
        log=log,
    )

    if staging_dir_config:
        dir_template = staging_dir_config["template"]["directory"]
        return StagingDir(
            dir_template.format_strict(ctx_data),
            is_persistent=staging_dir_config["persistence"],
            is_custom=True
        )

    # no config found but force an output
    if always_return_path:
        return StagingDir(
            get_temp_dir(
                project_name=project_entity["name"],
                anatomy=anatomy,
                prefix=prefix,
                suffix=suffix,
            ),
            is_persistent=False,
            is_custom=False
        )

    return None
