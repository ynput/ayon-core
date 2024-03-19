# -*- coding: utf-8 -*-
"""Collect user credentials

Requires:
    context -> project_settings

Provides:
    context -> deadline_require_authentication (bool)
    context -> deadline_auth (tuple (str, str)) - (username, password) or None
"""
import pyblish.api


class CollectUserCredentials(pyblish.api.ContextPlugin):
    """Collects user name and password for artist if DL requires authentication
    """

    # Run before collect_deadline_server_instance.
    order = pyblish.api.CollectorOrder
    label = "Collect Deadline User Credentials"

    def process(self, context):
        deadline_settings = context.data["project_settings"]["deadline"]

        context.data["deadline_require_authentication"] = (
            deadline_settings)["require_authentication"]
        context.data["deadline_auth"] = None

        if not context.data["deadline_require_authentication"]:
            return

        local_settings = deadline_settings["local_settings"]
        context.data["deadline_auth"] = (local_settings["username"],
                                         local_settings["password"])
