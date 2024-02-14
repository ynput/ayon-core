import logging
from ayon_core.pipeline import get_current_project_name

Session = {}

log = logging.getLogger(__name__)
log.warning(
    "DEPRECATION WARNING: 'legacy_io' is deprecated and will be removed in"
    " future versions of ayon-core addon."
    "\nReading from Session won't give you updated information and changing"
    " values won't affect global state of a process."
)


def session_data_from_environment(context_keys=False):
    return {}


def is_installed():
    return False


def install():
    pass


def uninstall():
    pass


def active_project(*args, **kwargs):
    return get_current_project_name()


def current_project(*args, **kwargs):
    return get_current_project_name()
