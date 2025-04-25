class MissingMethodsError(ValueError):
    """Exception when host miss some required methods for specific workflow.

    Args:
        host (HostBase): Host implementation where are missing methods.
        missing_methods (list[str]): List of missing methods.
    """

    def __init__(self, host, missing_methods):
        joined_missing = ", ".join(
            ['"{}"'.format(item) for item in missing_methods]
        )
        super().__init__(
            f"Host \"{host.name}\" miss methods {joined_missing}"
        )
