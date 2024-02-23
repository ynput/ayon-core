# -*- coding: utf-8 -*-
"""
Requires:
    instance.context.data["project_settings"]
Provides:
    instance.data["rr_root"] (str) - root folder of RoyalRender server
"""
import os.path

import pyblish.api
from ayon_core.modules.royalrender.rr_job import get_rr_platform


class CollectRRPathFromInstance(pyblish.api.InstancePlugin):
    """Collect RR Path from instance.

    All RoyalRender server roots are set in `Studio Settings`, each project
    uses only key pointing to that part to limit typos inside of Project
    settings.
    Eventually could be possible to add dropdown with these keys to the
    Creators to allow artists to select which RR server they would like to use.
    """

    order = pyblish.api.CollectorOrder
    label = "Collect Royal Render path name from the Instance"
    families = ["render", "prerender", "renderlayer"]

    def process(self, instance):
        instance.data["rr_root"] = self._collect_root(instance)
        self.log.info(
            "Using '{}' for submission.".format(instance.data["rr_root"]))

    def _collect_root(self, instance):
        # type: (pyblish.api.Instance) -> str
        """Get Royal Render pat name from render instance.
        If artist should be able to select specific RR server it must be added
        to creator. It is not there yet.
        """
        rr_settings = instance.context.data["project_settings"]["royalrender"]
        rr_paths = rr_settings["rr_paths"]
        selected_keys = rr_settings["selected_rr_paths"]

        platform = get_rr_platform()
        key_to_path = {
            item["name"]: item["value"][platform]
            for item in rr_paths
        }

        for selected_key in selected_keys:
            rr_root = key_to_path[selected_key]
            if os.path.exists(rr_root):
                return rr_root
