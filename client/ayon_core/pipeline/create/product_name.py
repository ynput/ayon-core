from __future__ import annotations

import warnings
from functools import wraps
from typing import Optional, Any

import ayon_api
from ayon_core.lib import (
    StringTemplate,
    filter_profiles,
    prepare_template_data,
    Logger,
    is_func_signature_supported,
)
from ayon_core.lib.path_templates import TemplateResult
from ayon_core.settings import get_project_settings

from .constants import DEFAULT_PRODUCT_TEMPLATE
from .exceptions import TaskNotSetError, TemplateFillError

log = Logger.get_logger(__name__)


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
            settings won't find any matching possibility. Constant
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
            .replace("{task}", "{task[name]}")
            .replace("{Task}", "{Task[name]}")
            .replace("{TASK}", "{TASK[NAME]}")
            .replace("{family}", "{product[type]}")
            .replace("{Family}", "{Product[type]}")
            .replace("{FAMILY}", "{PRODUCT[TYPE]}")
            .replace("{asset}", "{folder[name]}")
            .replace("{Asset}", "{Folder[name]}")
            .replace("{ASSET}", "{FOLDER[NAME]}")
        )

    # Make sure template is set (matching may have empty string)
    if not template:
        template = default_template or DEFAULT_PRODUCT_TEMPLATE
    return template


def _get_product_name_old(
    project_name: str,
    task_name: Optional[str],
    task_type: Optional[str],
    host_name: str,
    product_type: str,
    variant: str,
    default_template: Optional[str] = None,
    dynamic_data: Optional[dict[str, Any]] = None,
    project_settings: Optional[dict[str, Any]] = None,
    product_type_filter: Optional[str] = None,
    project_entity: Optional[dict[str, Any]] = None,
) -> TemplateResult:
    warnings.warn(
        "Used deprecated 'task_name' and 'task_type' arguments."
        " Please use new signature with 'folder_entity' and 'task_entity'.",
        DeprecationWarning,
        stacklevel=2
    )
    if not product_type:
        return StringTemplate("").format({})

    template = get_product_name_template(
        project_name,
        product_type_filter or product_type,
        task_name,
        task_type,
        host_name,
        default_template=default_template,
        project_settings=project_settings
    )

    template_low = template.lower()
    # Simple check of task name existence for template with {task[name]} in
    if not task_name and "{task" in template_low:
        raise TaskNotSetError()

    task_value = {
        "name": task_name,
        "type": task_type,
    }
    if "{task}" in template_low:
        task_value = task_name
        # NOTE this is message for TDs and Admins -> not really for users
        # TODO validate this in settings and not allow it
        log.warning(
            "Found deprecated task key '{task}' in product name template."
            " Please use '{task[name]}' instead."
        )

    elif "{task[short]}" in template_low:
        if project_entity is None:
            project_entity = ayon_api.get_project(project_name)
        task_types_by_name = {
            task["name"]: task for task in
            project_entity["taskTypes"]
        }
        task_short = task_types_by_name.get(task_type, {}).get("shortName")
        task_value["short"] = task_short

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
        return StringTemplate.format_strict_template(
            template=template,
            data=prepare_template_data(fill_pairs)
        )
    except KeyError as exp:
        raise TemplateFillError(
            "Value for {} key is missing in template '{}'."
            " Available values are {}".format(str(exp), template, fill_pairs)
        )


def _get_product_name(
    project_name: str,
    folder_entity: dict[str, Any],
    task_entity: Optional[dict[str, Any]],
    host_name: str,
    product_type: str,
    variant: str,
    *,
    default_template: Optional[str] = None,
    dynamic_data: Optional[dict[str, Any]] = None,
    project_settings: Optional[dict[str, Any]] = None,
    product_type_filter: Optional[str] = None,
    project_entity: Optional[dict[str, Any]] = None,
    # Ignore unused kwargs passed to 'get_product_name'
    task_name: Optional[str] = None,
    task_type: Optional[str] = None,
) -> TemplateResult:
    """Future replacement of 'get_product_name' function."""
    # Future warning when 'task_name' and 'task_type' are deprecated
    # if task_name is None:
    #     warnings.warn(
    #         "Still using deprecated 'task_name' argument. Please use"
    #         " 'task_entity' only.",
    #         DeprecationWarning,
    #         stacklevel=2
    #     )

    if not product_type:
        return StringTemplate("").format({})

    task_name = task_type = None
    if task_entity:
        task_name = task_entity["name"]
        task_type = task_entity["taskType"]

    template = get_product_name_template(
        project_name,
        product_type_filter or product_type,
        task_name,
        task_type,
        host_name,
        default_template=default_template,
        project_settings=project_settings
    )

    template_low = template.lower()
    # Simple check of task name existence for template with {task[name]} in
    if not task_name and "{task" in template_low:
        raise TaskNotSetError()

    task_value = {
        "name": task_name,
        "type": task_type,
    }
    if "{task}" in template_low:
        task_value = task_name
        # NOTE this is message for TDs and Admins -> not really for users
        # TODO validate this in settings and not allow it
        log.warning(
            "Found deprecated task key '{task}' in product name template."
            " Please use '{task[name]}' instead."
        )

    elif "{task[short]}" in template_low:
        if project_entity is None:
            project_entity = ayon_api.get_project(project_name)
        task_types_by_name = {
            task["name"]: task for task in
            project_entity["taskTypes"]
        }
        task_short = task_types_by_name.get(task_type, {}).get("shortName")
        task_value["short"] = task_short

    fill_pairs = {
        "variant": variant,
        # TODO We should stop support 'family' key.
        "family": product_type,
        "task": task_value,
        "product": {
            "type": product_type
        }
    }
    if folder_entity:
        fill_pairs["folder"] = {
            "name": folder_entity["name"],
            "type": folder_entity["folderType"],
        }

    if dynamic_data:
        # Dynamic data may override default values
        for key, value in dynamic_data.items():
            fill_pairs[key] = value

    try:
        return StringTemplate.format_strict_template(
            template=template,
            data=prepare_template_data(fill_pairs)
        )
    except KeyError as exp:
        raise TemplateFillError(
            f"Value for {exp} key is missing in template '{template}'."
            f" Available values are {fill_pairs}"
        )


def _get_product_name_decorator(func):
    """Helper to decide which variant of 'get_product_name' to use.

    The old version expected 'task_name' and 'task_type' arguments. The new
        version expects 'folder_entity' and 'task_entity' arguments instead.
    """
    # Add attribute to function to identify it as the new function
    #   so other addons can easily identify it.
    # >>> geattr(get_product_name, "use_entities", False)
    func.use_entities = True

    @wraps(_get_product_name)
    def inner(*args, **kwargs):
        # ---
        # Decide which variant of the function is used based on
        #   passed arguments.
        # ---

        # Entities in key-word arguments mean that the new function is used
        if "folder_entity" in kwargs or "task_entity" in kwargs:
            return func(*args, **kwargs)

        # Using more than 6 positional arguments is not allowed
        #   in the new function
        if len(args) > 6:
            return func(*args, **kwargs)

        if len(args) > 1:
            arg_2 = args[1]
            # Second argument is dictionary -> folder entity
            if isinstance(arg_2, dict):
                return func(*args, **kwargs)

        if is_func_signature_supported(func, *args, **kwargs):
            return func(*args, **kwargs)
        return _get_product_name_old(*args, **kwargs)

    return inner


def get_product_name(
    project_name: str,
    folder_entity: dict[str, Any],
    task_entity: Optional[dict[str, Any]],
    host_name: str,
    product_type: str,
    variant: str,
    *,
    default_template: Optional[str] = None,
    dynamic_data: Optional[dict[str, Any]] = None,
    project_settings: Optional[dict[str, Any]] = None,
    product_type_filter: Optional[str] = None,
    project_entity: Optional[dict[str, Any]] = None,
) -> TemplateResult:
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
        folder_entity (Optional[Dict[str, Any]]): Folder entity.
        task_entity (Optional[Dict[str, Any]]): Task entity.
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
        project_entity (Optional[Dict[str, Any]]): Project entity used when
            task short name is required by template.

    Returns:
        TemplateResult: Product name.

    Raises:
        TaskNotSetError: If template requires task which is not provided.
        TemplateFillError: If filled template contains placeholder key which
            is not collected.

    """
    return _get_product_name(
        project_name,
        folder_entity,
        task_entity,
        host_name,
        product_type,
        variant,
        default_template=default_template,
        dynamic_data=dynamic_data,
        project_settings=project_settings,
        product_type_filter=product_type_filter,
        project_entity=project_entity,
    )
