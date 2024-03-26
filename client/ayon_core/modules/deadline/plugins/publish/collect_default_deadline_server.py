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
    order = pyblish.api.CollectorOrder + 0.0025
    label = "Default Deadline Webservice"
    targets = ["local"]

    def process(self, context):
        try:
            deadline_module = context.data["ayonAddonsManager"]["deadline"]
        except AttributeError:
            self.log.error("Cannot get AYON Deadline addon.")
            raise AssertionError("AYON Deadline addon not found.")

        deadline_settings = context.data["project_settings"]["deadline"]
        deadline_server_name = deadline_settings["deadline_server"]

        dl_ws_item = None
        if deadline_server_name:
            dl_ws_item = deadline_module.deadline_server_info.get(
                deadline_server_name)

        if dl_ws_item:
            deadline_url = dl_ws_item["value"]
        else:
            default_dl_item = deadline_module.deadline_server_info.pop()
            deadline_url = default_dl_item["value"]

        context.data["deadline"] = {}
        context.data["deadline"]["defaultDeadline"] = (
            deadline_url.strip().rstrip("/"))
