import os
import inspect


class UnavailableSharedData(Exception):
    """Shared data are not available at the moment when are accessed."""
    pass


class ImmutableKeyError(TypeError):
    """Accessed key is immutable so does not allow changes or removals."""

    def __init__(self, key, msg=None):
        self.immutable_key = key
        if not msg:
            msg = "Key \"{}\" is immutable and does not allow changes.".format(
                key
            )
        super().__init__(msg)


class HostMissRequiredMethod(Exception):
    """Host does not have implemented required functions for creation."""

    def __init__(self, host, missing_methods):
        self.missing_methods = missing_methods
        self.host = host
        joined_methods = ", ".join(
            ['"{}"'.format(name) for name in missing_methods]
        )
        dirpath = os.path.dirname(
            os.path.normpath(inspect.getsourcefile(host))
        )
        dirpath_parts = dirpath.split(os.path.sep)
        host_name = dirpath_parts.pop(-1)
        if host_name == "api":
            host_name = dirpath_parts.pop(-1)

        msg = "Host \"{}\" does not have implemented method/s {}".format(
            host_name, joined_methods
        )
        super().__init__(msg)


class ConvertorsOperationFailed(Exception):
    def __init__(self, msg, failed_info):
        super().__init__(msg)
        self.failed_info = failed_info


class ConvertorsFindFailed(ConvertorsOperationFailed):
    def __init__(self, failed_info):
        msg = "Failed to find incompatible products"
        super().__init__(msg, failed_info)


class ConvertorsConversionFailed(ConvertorsOperationFailed):
    def __init__(self, failed_info):
        msg = "Failed to convert incompatible products"
        super().__init__(msg, failed_info)


class CreatorError(Exception):
    """Should be raised when creator failed because of known issue.

    Message of error should be artist friendly.
    """
    pass


class CreatorsOperationFailed(Exception):
    """Raised when a creator process crashes in 'CreateContext'.

    The exception contains information about the creator and error. The data
    are prepared using 'prepare_failed_creator_operation_info' and can be
    serialized using json.

    Usage is for UI purposes which may not have access to exceptions directly
    and would not have ability to catch exceptions 'per creator'.

    Args:
        msg (str): General error message.
        failed_info (list[dict[str, Any]]): List of failed creators with
            exception message and optionally formatted traceback.
    """

    def __init__(self, msg, failed_info):
        super().__init__(msg)
        self.failed_info = failed_info


class CreatorsCollectionFailed(CreatorsOperationFailed):
    def __init__(self, failed_info):
        msg = "Failed to collect instances"
        super().__init__(msg, failed_info)


class CreatorsSaveFailed(CreatorsOperationFailed):
    def __init__(self, failed_info):
        msg = "Failed update instance changes"
        super().__init__(msg, failed_info)


class CreatorsRemoveFailed(CreatorsOperationFailed):
    def __init__(self, failed_info):
        msg = "Failed to remove instances"
        super().__init__(msg, failed_info)


class CreatorsCreateFailed(CreatorsOperationFailed):
    def __init__(self, failed_info):
        msg = "Failed to create instances"
        super().__init__(msg, failed_info)


class TaskNotSetError(KeyError):
    def __init__(self, msg=None):
        if not msg:
            msg = "Creator's product name template requires task name."
        super().__init__(msg)


class TemplateFillError(Exception):
    def __init__(self, msg=None):
        if not msg:
            msg = "Creator's product name template is missing key value."
        super().__init__(msg)
