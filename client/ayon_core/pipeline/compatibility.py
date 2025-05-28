"""Package to handle compatibility checks for pipeline components."""


def is_supporting_product_base_type() -> bool:
    """Check support for product base types.

    This function checks if the current pipeline supports product base types.
    Once this feature is implemented, it will return True. This should be used
    in places where some kind of backward compatibility is needed to avoid
    breaking existing functionality that relies on the current behavior.

    Returns:
        bool: True if product base types are supported, False otherwise.

    """
    return False
