from ayon_core.lib import Logger, filter_profiles, StringTemplate
from ayon_core.settings import get_project_settings
from ayon_core.pipeline.template_data import get_template_data

from .anatomy import Anatomy
from .tempdir import get_temp_dir

STAGING_DIR_TEMPLATES = "staging"


def get_staging_dir_config(
    host_name,
    project_name,
    task_type,
    task_name,
    product_type,
    product_name,
    project_settings=None,
    anatomy=None,
    log=None,
):
    """Get matching staging dir profile.

    Args:
        host_name (str): Name of host.
        project_name (str): Name of project.
        task_type (str): Type of task.
        task_name (str): Name of task.
        product_type (str): Type of product.
        product_name (str): Name of product.
        project_settings(Dict[str, Any]): Prepared project settings.
        anatomy (Dict[str, Any])
        log (Optional[logging.Logger])

    Returns:
        Dict or None: Data with directory template and is_persistent or None

    Raises:
        ValueError - if misconfigured template should be used

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

    template = anatomy.templates[STAGING_DIR_TEMPLATES][template_name]

    if not template:
        # template should always be found either from anatomy or from profile
        raise ValueError(
            "Staging dir profile is misconfigured! "
            "No template was found for profile! "
            "Check your project settings at: "
            "'ayon+settings://core/tools/publish/custom_staging_dir_profiles'"
        )

    data_persistence = profile["custom_staging_dir_persistent"]

    return {"template": template, "persistence": data_persistence}


def _validate_template_name(project_name, template_name, anatomy):
    """Check that staging dir section with appropriate template exist.

    Raises:
        ValueError - if misconfigured template
    """
    if template_name not in anatomy.templates[STAGING_DIR_TEMPLATES]:
        raise ValueError(
            (
                'Anatomy of project "{}" does not have set'
                ' "{}" template key at Staging Dir section!'
            ).format(project_name, template_name)
        )


def get_staging_dir_info(
    host_name,
    project_entity,
    folder_entity,
    task_entity,
    product_type,
    product_name,
    anatomy,
    project_settings=None,
    template_data=None,
    always_return_path=None,
    force_tmp_dir=None,
    logger=None,
    **kwargs
):
    """Get staging dir info data.

    If `force_temp` is set, staging dir will be created as tempdir.
    If `always_get_some_dir` is set, staging dir will be created as tempdir if
    no staging dir profile is found.
    If `prefix` or `suffix` is not set, default values will be used.

    Arguments:
        host_name (str): Name of host.
        project_entity (Dict[str, Any]): Project entity.
        folder_entity (Dict[str, Any]): Folder entity.
        task_entity (Dict[str, Any]): Task entity.
        product_type (str): Type of product.
        product_name (str): Name of product.
        anatomy (ayon_core.pipeline.Anatomy): Anatomy object.
        project_settings (Optional[Dict[str, Any]]): Prepared project settings.
        template_data (Optional[Dict[str, Any]]): Data for formatting staging
            dir template.
        always_return_path (Optional[bool]): If True, staging dir will be
            created as tempdir if no staging dir profile is found. Input value
            False will return None if no staging dir profile is found.
        force_tmp_dir (Optional[bool]): If True, staging dir will be created as
            tempdir.
        logger (Optional[logging.Logger]): Logger instance.
        **kwargs: Arbitrary keyword arguments. See below.

    Keyword Arguments:
        prefix (str): Prefix for staging dir.
        suffix (str): Suffix for staging dir.

    Returns:
        Optional[Dict[str, Any]]: Staging dir info data

    """
    log = logger or Logger.get_logger("get_staging_dir_info")

    # make sure always_return_path is set to true by default
    if always_return_path is None:
        always_return_path = True

    if force_tmp_dir:
        return get_temp_dir(
            project_name=project_entity["name"],
            anatomy=anatomy,
            prefix=kwargs.get("prefix"),
            suffix=kwargs.get("suffix"),
        )

    # making fewer queries to database
    ctx_data = get_template_data(
        project_entity, folder_entity, task_entity, host_name
    )

    # add additional data
    ctx_data.update({
        "product": {
            "type": product_type,
            "name": product_name
        },
        "root": anatomy.roots
    })

    # add additional template formatting data
    if template_data:
        ctx_data.update(template_data)

    # get staging dir config
    staging_dir_config = get_staging_dir_config(
        host_name,
        project_entity["name"],
        task_entity["type"],
        task_entity["name"],
        product_type,
        product_name,
        project_settings=project_settings,
        anatomy=anatomy,
        log=log,
    )

    # if no preset matching and always_get_some_dir is set, return tempdir
    if not staging_dir_config and always_return_path:
        return {
            "stagingDir": get_temp_dir(
                project_name=project_entity["name"],
                anatomy=anatomy,
                prefix=kwargs.get("prefix"),
                suffix=kwargs.get("suffix"),
            ),
            "stagingDir_persistent": False,
        }
    if not staging_dir_config:
        return None

    return {
        "stagingDir": StringTemplate.format_template(
            staging_dir_config["template"], ctx_data
        ),
        "stagingDir_persistent": staging_dir_config["persistence"],
    }
