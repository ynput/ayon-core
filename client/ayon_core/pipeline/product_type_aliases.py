"""Tools for working with product type aliases."""
from __future__ import annotations

from typing import Optional

def get_product_type_aliases(project_settings: dict) -> list[dict[str,str]]:
    """Get product type aliases from project settings.

    Args:
        project_settings (dict): Project settings.

    Returns:
        list[dict[str, str]: A list of product type aliases.

    """
    product_type_aliases_raw = project_settings["core"].get(
        "product_type_aliases", {})
    if not product_type_aliases_raw:
        return {}

    return product_type_aliases_raw.get("aliases", {})


def get_alias_for_product_type(
        product_type: str,
        project_settings: dict
    ) -> str:
    """Get the alias for a product type.

    Args:
        product_type (str): The product type to get the alias for.
        project_settings (dict): Project settings.
            Defaults to None. If not passed, the current project settings
            will be used.

    Returns:
        str: The alias for the product type. If no alias is found,
            product_type is returned.
    """
    product_type_aliases: list = get_product_type_aliases(project_settings)

    return next(
        (
            alias_pair.get("alias")
            for alias_pair in product_type_aliases
            if alias_pair.get("base") == product_type
        ),
        product_type,
    )
