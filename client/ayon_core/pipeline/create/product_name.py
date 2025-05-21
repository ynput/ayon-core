"""Functions for product name resolution."""
from __future__ import annotations

from copy import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

import ayon_api

from ayon_core.lib import (
    StringTemplate,
    filter_profiles,
    prepare_template_data,
)
from ayon_core.settings import get_project_settings

from .constants import DEFAULT_PRODUCT_TEMPLATE
from .exceptions import TaskNotSetError, TemplateFillError

if TYPE_CHECKING:
    from ayon_core.pipeline.create.base_product_types import BaseProductType


@dataclass
class ProductContext:
    """Product context for product name resolution.

    To get the product name, we need to know the context in which the product
    is created. This context is defined by the project name, task name,
    task type, host name, product base type and variant. The context is
    passed to the `get_product_name` function, which uses it to resolve the
    product name based on the AYON settings.

    Args:
        project_name (str): Project name.
        task_name (str): Task name.
        task_type (str): Task type.
        host_name (str): Host name.
        product_base_type (BaseProductType): Product base type.
        variant (str): Variant value.
        product_type (Optional[str]): Product type.

    """

    project_name: str
    task_name: str
    task_type: str
    host_name: str
    product_base_type: BaseProductType
    variant: str
    product_type: Optional[str] = None


def get_product_name_template(
    context: ProductContext,
    default_template: Optional[str] = None,
    project_settings: Optional[dict] = None
) -> str:
    """Get product name template based on passed context.

    Args:
        context (ProductContext): Product context.
        default_template (Optional[str]): Default template which is used if
            settings won't find any matching possibility. Constant
            'DEFAULT_PRODUCT_TEMPLATE' is used if not defined.
        project_settings (Optional[Dict[str, Any]]): Prepared settings for
            project. Settings are queried if not passed.

    Returns:
        str: Product name template.

    """
    if project_settings is None:
        project_settings = get_project_settings(context.project_name)

    if not context.product_type:
        context.product_type = context.product_base_type.name

    tools_settings = project_settings["core"]["tools"]
    profiles = tools_settings["creator"]["product_name_profiles"]
    filtering_criteria = {
        "product_types": context.product_type,
        "hosts": context.host_name,
        "tasks": context.task_name,
        "task_types": context.task_type
    }

    matching_profile = filter_profiles(profiles, filtering_criteria)
    template = None
    if matching_profile:
        template = matching_profile["template"]
    # Make sure template is set (matching may have empty string)
    if not template:
        template = default_template or DEFAULT_PRODUCT_TEMPLATE
    return template


def get_product_name(
    context: ProductContext,
    default_template: Optional[str] = None,
    dynamic_data: Optional[dict] = None,
    project_settings: Optional[dict] = None,
    product_type_filter: Optional[str] = None,
    project_entity: Optional[dict] = None,
) -> str:
    """Calculate product name based on passed context and AYON settings.

    Subst name templates are defined in `project_settings/global/tools/creator
    /product_name_profiles` where are profiles with host name, product type,
    task name and task type filters. If context does not match any profile
    then `DEFAULT_PRODUCT_TEMPLATE` is used as default template.

    That's main reason why so many arguments are required to calculate product
    name.

    Args:
        context (ProductContext): Product context.
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
        str: Product name.

    Raises:
        TaskNotSetError: If template requires task which is not provided.
        TemplateFillError: If filled template contains placeholder key which
            is not collected.

    """
    # Product type was mandatory. If it is missing, use name from base type
    # to avoid breaking changes.
    if context.product_type is None:
        product_type = context.product_base_type.name

    template_context = copy(context)
    if product_type_filter:
        template_context.product_type = product_type_filter

    template = get_product_name_template(
        template_context,
        default_template=default_template,
        project_settings=project_settings
    )
    # Simple check of task name existence for template with {task} in
    #   - missing task should be possible only in Standalone publisher
    if not context.task_name and "{task" in template.lower():
        raise TaskNotSetError

    task_value = {
        "name": context.task_name,
        "type": context.task_type,
    }

    # task_value can be for backwards compatibility
    # single string or dict
    if "{task}" in template.lower():
        task_value = context.task_name  # type: ignore[assignment]

    elif "{task[short]}" in template.lower():
        if project_entity is None:
            project_entity = ayon_api.get_project(context.project_name)
        task_types_by_name = {
            task["name"]: task for task in
            project_entity["taskTypes"]
        }
        task_short = task_types_by_name.get(
            context.task_type, {}).get("shortName")
        task_value["short"] = task_short

    fill_pairs = {
        "variant": context.variant,
        "family": product_type,
        "task": task_value,
        "product": {
            "type": product_type,
            "base": context.product_base_type.name
        }
    }
    if dynamic_data:
        # Dynamic data may override default values
        fill_pairs = dict(dynamic_data.items())

    try:
        return StringTemplate.format_strict_template(
            template=template, data=prepare_template_data(fill_pairs)
        )
    except KeyError as exp:
        msg = (
            f"Value for {exp} key is missing in template '{template}'."
            f" Available values are {fill_pairs}"
        )
        raise TemplateFillError(msg) from exp
