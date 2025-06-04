"""Functions for handling product names."""
from __future__ import annotations

from typing import Any, Optional, Union
from warnings import warn

import ayon_api
from ayon_core.lib import (
    StringTemplate,
    filter_profiles,
    prepare_template_data,
)
from ayon_core.pipeline.compatibility import is_supporting_product_base_type
from ayon_core.settings import get_project_settings

from .constants import DEFAULT_PRODUCT_TEMPLATE
from .exceptions import TaskNotSetError, TemplateFillError


def get_product_name_template(
    project_name: str,
    product_type: str,
    task_name: str,
    task_type: str,
    host_name: str,
    default_template: Optional[str] = None,
    project_settings: Optional[dict[str, Any]] = None,
    product_base_type: Optional[str] = None
) -> str:
    """Get product name template based on passed context.

    Args:
        project_name (str): Project on which the context lives.
        product_type (str): Product type for which the product name is
            calculated.
        host_name (str): Name of host in which the product name is calculated.
        task_name (str): Name of task in which context the product is created.
        task_type (str): Type of task in which context the product is created.
        default_template (Optional, str): Default template which is used if
            settings won't find any matching possibility. Constant
            'DEFAULT_PRODUCT_TEMPLATE' is used if not defined.
        project_settings (Union[Dict[str, Any], None]): Prepared settings for
            project. Settings are queried if not passed.
        product_base_type (Optional[str]): Base type of product.

    Returns:
        str: Product name template.

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

    if is_supporting_product_base_type():
        if product_base_type:
            filtering_criteria["product_base_types"] = product_base_type
        else:
            warn(
                "Product base type is not provided, please update your"
                "creation code to include it. It will be required in "
                "the future.", DeprecationWarning, stacklevel=2)

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


def get_product_name(
    project_name: str,
    task_name: str,
    task_type: str,
    host_name: str,
    product_type: str,
    variant: str,
    default_template: Optional[str] = None,
    dynamic_data: Optional[dict[str, Any]] = None,
    project_settings: Optional[dict[str, Any]] = None,
    product_type_filter: Optional[str] = None,
    project_entity: Optional[dict[str, Any]] = None,
    product_base_type: Optional[str] = None
):
    """Calculate product name based on passed context and AYON settings.

    Subst name templates are defined in `project_settings/global/tools/creator
    /product_name_profiles` where are profiles with host name, product type,
    task name and task type filters. If context does not match any profile
    then `DEFAULT_PRODUCT_TEMPLATE` is used as default template.

    That's main reason why so many arguments are required to calculate product
    name.

    Deprecation:
        The `product_base_type` argument is optional now, but it will be
        mandatory in future versions. It is recommended to pass it now to
        avoid issues in the future. If it is not passed, a warning will be
        raised to inform about this change.

    Todos:
        Find better filtering options to avoid requirement of
            argument 'family_filter'.

    Args:
        project_name (str): Project name.
        task_name (str): Task name.
        task_type (str): Task type.
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
        product_base_type (Optional[str]): Base type of product.
            This will be mandatory in future versions.

    Returns:
        str: Product name.

    Raises:
        TaskNotSetError: If template requires task which is not provided.
        TemplateFillError: If filled template contains placeholder key which
            is not collected.

    """
    if not product_type:
        return ""

    template = get_product_name_template(
        project_name=project_name,
        product_type=product_type_filter or product_type,
        task_name=task_name,
        task_type=task_type,
        host_name=host_name,
        default_template=default_template,
        project_settings=project_settings,
        product_base_type=product_base_type,
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
        task_value["name"] = task_name

    elif "{task[short]}" in template.lower():
        if project_entity is None:
            project_entity = ayon_api.get_project(project_name)
        task_types_by_name = {
            task["name"]: task for task in
            project_entity["taskTypes"]
        }
        task_short = task_types_by_name.get(task_type, {}).get("shortName")
        task_value["short"] = task_short

    # look what we have to do to make mypy happy. We should stop using
    # those undefined dict based types.
    product: dict[str, str] = {"type": product_type}
    if is_supporting_product_base_type():
        if product_base_type:
            product["baseType"] = product_base_type
        elif "{product[basetype]}" in template.lower():
            warn(
                "You have Product base type in product name template,"
                "but it is not provided by the creator, please update your"
                "creation code to include it. It will be required in "
                "the future.", DeprecationWarning, stacklevel=2)
    fill_pairs: dict[str, Union[str, dict[str, str]]] = {
        "variant": variant,
        "family": product_type,
        "task": task_value,
        "product": product,
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
        msg = (
            f"Value for {exp} key is missing in template '{template}'."
            f" Available values are {fill_pairs}"
        )
        raise TemplateFillError(msg) from exp
