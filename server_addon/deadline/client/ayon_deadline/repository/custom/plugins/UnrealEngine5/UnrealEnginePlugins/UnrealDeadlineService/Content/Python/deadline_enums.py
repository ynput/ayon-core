# Built-in
from enum import Enum, auto


class AutoRequestName(Enum):
    """
    Function to auto generate the enum value from its name.
    Reference: https://docs.python.org/3/library/enum.html#using-automatic-values
    """
    def _generate_next_value_(name, start, count, last_values):
        return name


class HttpRequestType(AutoRequestName):
    """
    Enum class for HTTP request types
    """
    GET = auto()
    PUT = auto()
    POST = auto()
    DELETE = auto()


class DeadlineJobState(Enum):
    """Enum class for deadline states"""

    SUSPEND = "suspend"
    RESUME = "resume"
    REQUEUE = "requeue"
    PEND = "pend"
    ARCHIVE = "archive"
    RESUME_FAILED = "resumefailed"
    SUSPEND_NON_RENDERING = "suspendnonrendering"
    RELEASE_PENDING = "releasepending"
    COMPLETE = "complete"
    FAIL = "fail"
    UPDATE_SUBMISSION_DATE = "updatesubmissiondate"
    UNDELETE = "undelete"


class DeadlineJobStatus(Enum):
    """
    Enum class for deadline job status
    Reference: https://docs.thinkboxsoftware.com/products/deadline/10.1/1_User%20Manual/manual/rest-jobs.html#job-property-values
    """

    UNKNOWN = "Unknown"
    ACTIVE = "Active"
    SUSPENDED = "Suspended"
    COMPLETED = "Completed"
    FAILED = "Failed"
    RENDERING = "Rendering"
    PENDING = "Pending"
    IDLE = "Idle"
    QUEUED = "Queued"
