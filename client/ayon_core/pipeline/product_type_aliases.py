"""Tools for working with product type aliases."""
from __future__ import annotations

from typing import Optional

from ayon_core.settings import get_project_settings
from ayon_core.pipeline import get_current_project_name

def get_product_type_aliases(
        project_settings: Optional[dict] = None) -> dict[str, str]:
    """Get product type aliases from project settings.

    Args:
        project_settings (Optional[dict], optional): Project settings.
            Defaults to None. If not passed, the current project settings
            will be used.

    Returns:
        dict[str, str]: A dictionary of product type aliases.

    """
    if project_settings is None:
        project_settings = get_project_settings(
            project_name=get_current_project_name())

    product_type_aliases_raw = project_settings.get("product_type_aliases", {})
    if not product_type_aliases_raw:
        return {}

    return product_type_aliases_raw.get("aliases", {})


def get_alias_for_product_type(
        product_type: str,
        project_settings: Optional[dict] = None
    ) -> Optional[str]:
    """Get the alias for a product type.

    Args:
        product_type (str): The product type to get the alias for.
        project_settings (Optional[dict], optional): Project settings.
            Defaults to None. If not passed, the current project settings
            will be used.

    Returns:
        str: The alias for the product type. If no alias is found,
            None is returned.
    """
    product_type_aliases = get_product_type_aliases(project_settings)
    return product_type_aliases.get(product_type)
