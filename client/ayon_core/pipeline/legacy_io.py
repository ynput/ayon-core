"""Wrapper around interactions with the database"""

import os
import sys
import logging
import functools

from . import schema

module = sys.modules[__name__]

Session = {}
_is_installed = False

log = logging.getLogger(__name__)

SESSION_CONTEXT_KEYS = (
    # Name of current Project
    "AVALON_PROJECT",
    # Name of current Asset
    "AVALON_ASSET",
    # Name of current task
    "AVALON_TASK",
    # Name of current app
    "AVALON_APP",
    # Path to working directory
    "AVALON_WORKDIR",
    # Optional path to scenes directory (see Work Files API)
    "AVALON_SCENEDIR"
)


def session_data_from_environment(context_keys=False):
    session_data = {}
    if context_keys:
        for key in SESSION_CONTEXT_KEYS:
            value = os.environ.get(key)
            session_data[key] = value or ""
    else:
        for key in SESSION_CONTEXT_KEYS:
            session_data[key] = None

    for key, default_value in (
        # Name of Avalon in graphical user interfaces
        # Use this to customise the visual appearance of Avalon
        # to better integrate with your surrounding pipeline
        ("AVALON_LABEL", "Avalon"),

        # Used during any connections to the outside world
        ("AVALON_TIMEOUT", "1000"),

        # Name of database used in MongoDB
        ("AVALON_DB", "avalon"),
    ):
        value = os.environ.get(key) or default_value
        if value is not None:
            session_data[key] = value

    return session_data


def is_installed():
    return module._is_installed


def install():
    """Establish a persistent connection to the database"""
    if is_installed():
        return

    session = session_data_from_environment(context_keys=True)

    session["schema"] = "openpype:session-4.0"
    try:
        schema.validate(session)
    except schema.ValidationError as e:
        # TODO(marcus): Make this mandatory
        log.warning(e)

    Session.update(session)

    module._is_installed = True


def uninstall():
    """Close any connection to the database.

    Deprecated:
        This function does nothing should be removed.
    """
    module._is_installed = False


def requires_install(func):
    @functools.wraps(func)
    def decorated(*args, **kwargs):
        if not is_installed():
            install()
        return func(*args, **kwargs)
    return decorated


@requires_install
def active_project(*args, **kwargs):
    return Session["AVALON_PROJECT"]


def current_project(*args, **kwargs):
    return Session.get("AVALON_PROJECT")
