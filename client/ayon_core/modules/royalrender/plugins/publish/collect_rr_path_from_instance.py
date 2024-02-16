# -*- coding: utf-8 -*-
import pyblish.api


class CollectRRPathFromInstance(pyblish.api.InstancePlugin):
    """Collect RR Path from instance."""

    order = pyblish.api.CollectorOrder
    label = "Collect Royal Render path name from the Instance"
    families = ["render", "prerender", "renderlayer"]

    def process(self, instance):
        instance.data["rrPathName"] = self._collect_rr_path_name(instance)
        self.log.info(
            "Using '{}' for submission.".format(instance.data["rrPathName"]))

    @staticmethod
    def _collect_rr_path_name(instance):
        # type: (pyblish.api.Instance) -> str
        """Get Royal Render pat name from render instance."""

        instance_rr_paths = instance.data.get("rrPaths")
        if instance_rr_paths is None:
            return "default"

        rr_settings = instance.context.data["project_settings"]["royalrender"]
        rr_paths = rr_settings["rr_paths"]
        selected_paths = rr_settings["selected_rr_paths"]

        rr_servers = {
            path_key
            for path_key in selected_paths
            if path_key in rr_paths
        }
        for instance_rr_path in instance_rr_paths:
            if instance_rr_path in rr_servers:
                return instance_rr_path
        return "default"
