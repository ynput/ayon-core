from ayon_core.settings import get_project_settings
from ayon_core.lib import filter_profiles, prepare_template_data

from .constants import DEFAULT_PRODUCT_TEMPLATE


class TaskNotSetError(KeyError):
    def __init__(self, msg=None):
        if not msg:
            msg = "Creator's product name template requires task name."
        super(TaskNotSetError, self).__init__(msg)


class TemplateFillError(Exception):
    def __init__(self, msg=None):
        if not msg:
            msg = "Creator's product name template is missing key value."
        super(TemplateFillError, self).__init__(msg)


def get_product_name_template(
    project_name,
    product_type,
    task_name,
    task_type,
    host_name,
    default_template=None,
    project_settings=None
):
    """Get product name template based on passed context.

    Args:
        project_name (str): Project on which the context lives.
        product_type (str): Product type for which the product name is
            calculated.
        host_name (str): Name of host in which the product name is calculated.
        task_name (str): Name of task in which context the product is created.
        task_type (str): Type of task in which context the product is created.
        default_template (Union[str, None]): Default template which is used if
            settings won't find any matching possitibility. Constant
            'DEFAULT_PRODUCT_TEMPLATE' is used if not defined.
        project_settings (Union[Dict[str, Any], None]): Prepared settings for
            project. Settings are queried if not passed.
    """

    if project_settings is None:
        project_settings = get_project_settings(project_name)
    tools_settings = project_settings["core"]["tools"]
    profiles = tools_settings["creator"]["product_name_profiles"]
    filtering_criteria = {
        "product_types": product_type,
        "hosts": host_name,
        "tasks": task_name,
        "task_types": task_type
    }

    matching_profile = filter_profiles(profiles, filtering_criteria)
    template = None
    if matching_profile:
        # TODO remove formatting keys replacement
        template = (
            matching_profile["template"]
            .replace("{task[name]}", "{task}")
            .replace("{Task[name]}", "{Task}")
            .replace("{TASK[NAME]}", "{TASK}")
            .replace("{product[type]}", "{family}")
            .replace("{Product[type]}", "{Family}")
            .replace("{PRODUCT[TYPE]}", "{FAMILY}")
            .replace("{folder[name]}", "{asset}")
            .replace("{Folder[name]}", "{Asset}")
            .replace("{FOLDER[NAME]}", "{ASSET}")
        )

    # Make sure template is set (matching may have empty string)
    if not template:
        template = default_template or DEFAULT_PRODUCT_TEMPLATE
    return template


def get_product_name(
    project_name,
    task_name,
    task_type,
    host_name,
    product_type,
    variant,
    default_template=None,
    dynamic_data=None,
    project_settings=None,
    product_type_filter=None,
):
    """Calculate product name based on passed context and AYON settings.

    Subst name templates are defined in `project_settings/global/tools/creator
    /product_name_profiles` where are profiles with host name, product type,
    task name and task type filters. If context does not match any profile
    then `DEFAULT_PRODUCT_TEMPLATE` is used as default template.

    That's main reason why so many arguments are required to calculate product
    name.

    Todos:
        Find better filtering options to avoid requirement of
            argument 'family_filter'.

    Args:
        project_name (str): Project name.
        task_name (Union[str, None]): Task name.
        task_type (Union[str, None]): Task type.
        host_name (str): Host name.
        product_type (str): Product type.
        variant (str): In most of the cases it is user input during creation.
        default_template (Optional[str]): Default template if any profile does
            not match passed context. Constant 'DEFAULT_PRODUCT_TEMPLATE'
            is used if is not passed.
        dynamic_data (Optional[Dict[str, Any]]): Dynamic data specific for
            a creator which creates instance.
        project_settings (Optional[Union[Dict[str, Any]]]): Prepared settings
            for project. Settings are queried if not passed.
        product_type_filter (Optional[str]): Use different product type for
            product template filtering. Value of `product_type` is used when
            not passed.

    Raises:
        TemplateFillError: If filled template contains placeholder key which
            is not collected.
    """

    if not product_type:
        return ""

    template = get_product_name_template(
        project_name,
        product_type_filter or product_type,
        task_name,
        task_type,
        host_name,
        default_template=default_template,
        project_settings=project_settings
    )
    # Simple check of task name existence for template with {task} in
    #   - missing task should be possible only in Standalone publisher
    if not task_name and "{task" in template.lower():
        raise TaskNotSetError()

    task_value = {
        "name": task_name,
        "type": task_type,
    }
    if "{task}" in template.lower():
        task_value = task_name

    fill_pairs = {
        "variant": variant,
        "family": product_type,
        "task": task_value,
        "product": {
            "type": product_type
        }
    }
    if dynamic_data:
        # Dynamic data may override default values
        for key, value in dynamic_data.items():
            fill_pairs[key] = value

    try:
        return template.format(**prepare_template_data(fill_pairs))
    except KeyError as exp:
        raise TemplateFillError(
            "Value for {} key is missing in template '{}'."
            " Available values are {}".format(str(exp), template, fill_pairs)
        )
