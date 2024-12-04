from dataclasses import dataclass

from ayon_core.lib import Logger, filter_profiles
from ayon_core.settings import get_project_settings

from .template_data import get_template_data
from .anatomy import Anatomy
from .tempdir import get_temp_dir


@dataclass
class StagingDir:
    directory: str
    persistent: bool


def get_staging_dir_config(
    project_name,
    task_type,
    task_name,
    product_type,
    product_name,
    host_name,
    project_settings=None,
    anatomy=None,
    log=None,
):
    """Get matching staging dir profile.

    Args:
        host_name (str): Name of host.
        project_name (str): Name of project.
        task_type (Optional[str]): Type of task.
        task_name (Optional[str]): Name of task.
        product_type (str): Type of product.
        product_name (str): Name of product.
        project_settings(Dict[str, Any]): Prepared project settings.
        anatomy (Dict[str, Any])
        log (Optional[logging.Logger])

    Returns:
        Dict or None: Data with directory template and is_persistent or None

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
        "hosts": host_name,
        "task_types": task_type,
        "task_names": task_name,
        "product_types": product_type,
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
    _validate_template_name(project_name, template_name, anatomy)

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


def _validate_template_name(project_name, template_name, anatomy):
    """Check that staging dir section with appropriate template exist.

    Raises:
        ValueError - if misconfigured template
    """
    if template_name not in anatomy.templates["staging"]:
        raise ValueError(
            f'Anatomy of project "{project_name}" does not have set'
            f' "{template_name}" template key at Staging Dir category!'
        )


def get_staging_dir_info(
    project_entity,
    folder_entity,
    task_entity,
    product_type,
    product_name,
    host_name,
    anatomy=None,
    project_settings=None,
    template_data=None,
    always_return_path=True,
    force_tmp_dir=False,
    logger=None,
    prefix=None,
    suffix=None,
):
    """Get staging dir info data.

    If `force_temp` is set, staging dir will be created as tempdir.
    If `always_get_some_dir` is set, staging dir will be created as tempdir if
    no staging dir profile is found.
    If `prefix` or `suffix` is not set, default values will be used.

    Arguments:
        project_entity (Dict[str, Any]): Project entity.
        folder_entity (Optional[Dict[str, Any]]): Folder entity.
        task_entity (Optional[Dict[str, Any]]): Task entity.
        product_type (str): Type of product.
        product_name (str): Name of product.
        host_name (str): Name of host.
        anatomy (Optional[Anatomy]): Anatomy object.
        project_settings (Optional[Dict[str, Any]]): Prepared project settings.
        template_data (Optional[Dict[str, Any]]): Additional data for
            formatting staging dir template.
        always_return_path (Optional[bool]): If True, staging dir will be
            created as tempdir if no staging dir profile is found. Input value
            False will return None if no staging dir profile is found.
        force_tmp_dir (Optional[bool]): If True, staging dir will be created as
            tempdir.
        logger (Optional[logging.Logger]): Logger instance.
        prefix (Optional[str]) Optional prefix for staging dir name.
        suffix (Optional[str]): Optional suffix for staging dir name.

    Returns:
        Optional[StagingDir]: Staging dir info data

    """
    log = logger or Logger.get_logger("get_staging_dir_info")

    if anatomy is None:
        anatomy = Anatomy(
            project_entity["name"], project_entity=project_entity
        )

    if force_tmp_dir:
        return get_temp_dir(
            project_name=project_entity["name"],
            anatomy=anatomy,
            prefix=prefix,
            suffix=suffix,
        )

    # making few queries to database
    ctx_data = get_template_data(
        project_entity, folder_entity, task_entity, host_name
    )

    # add additional data
    ctx_data["product"] = {
        "type": product_type,
        "name": product_name
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
        task_name ,
        product_type,
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
            staging_dir_config["persistence"],
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
            False,
        )

    return None
