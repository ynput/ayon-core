# -*- coding: utf-8 -*-
"""Collect instance members."""
import pyblish.api
from pymxs import runtime as rt


class CollectMembers(pyblish.api.InstancePlugin):
    """Collect Set Members."""

    order = pyblish.api.CollectorOrder + 0.01
    label = "Collect Instance Members"
    hosts = ['max']

    def process(self, instance):
        if instance.data["productType"] in {
            "workfile", "tyflow", "tycache", "tyspline"}:
                self.log.debug(
                    "Skipping Collecting Members for workfile "
                    "and tyflow product type."
                )
                return

        elif instance.data.get("instance_node"):
            container = rt.GetNodeByName(instance.data["instance_node"])
            instance.data["members"] = [
                member.node for member
                in container.modifiers[0].openPypeData.all_handles
            ]
