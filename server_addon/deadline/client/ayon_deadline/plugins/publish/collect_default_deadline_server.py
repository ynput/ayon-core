# -*- coding: utf-8 -*-
"""Collect default Deadline server."""
import pyblish.api


class CollectDefaultDeadlineServer(pyblish.api.ContextPlugin):
    """Collect default Deadline Webservice URL.

    DL webservice addresses must be configured first in System Settings for
    project settings enum to work.

    Default webservice could be overridden by
    `project_settings/deadline/deadline_servers`. Currently only single url
    is expected.

    This url could be overridden by some hosts directly on instances with
    `CollectDeadlineServerFromInstance`.
    """

    # Run before collect_deadline_server_instance.
    order = pyblish.api.CollectorOrder + 0.200
    label = "Default Deadline Webservice"
    targets = ["local"]

    def process(self, context):
        try:
            deadline_addon = context.data["ayonAddonsManager"]["deadline"]
        except AttributeError:
            self.log.error("Cannot get AYON Deadline addon.")
            raise AssertionError("AYON Deadline addon not found.")

        deadline_settings = context.data["project_settings"]["deadline"]
        deadline_server_name = deadline_settings["deadline_server"]

        dl_server_info = None
        if deadline_server_name:
            dl_server_info = deadline_addon.deadline_servers_info.get(
                deadline_server_name)

        if dl_server_info:
            deadline_url = dl_server_info["value"]
        else:
            default_dl_server_info = deadline_addon.deadline_servers_info[0]
            deadline_url = default_dl_server_info["value"]

        context.data["deadline"] = {}
        context.data["deadline"]["defaultUrl"] = (
            deadline_url.strip().rstrip("/"))
