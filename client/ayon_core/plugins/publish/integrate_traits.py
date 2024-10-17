"""Integrate representations with traits."""
import logging

import pyblish.api

from ayon_core.pipeline.publish import (
    get_publish_template_name,
)
from ayon_core.pipeline.traits import Persistent, Representation


class IntegrateTraits(pyblish.api.InstancePlugin):
    """Integrate representations with traits."""

    label = "Integrate Asset"
    order = pyblish.api.IntegratorOrder
    log: logging.Logger

    def process(self, instance: pyblish.api.Instance) -> None:
        """Integrate representations with traits.

        Args:
            instance (pyblish.api.Instance): Instance to process.

        """
        # 1) skip farm and integrate ==  False

        if not instance.data.get("integrate"):
            self.log.debug("Instance is marked to skip integrating. Skipping")
            return

        if instance.data.get("farm"):
            self.log.debug(
                "Instance is marked to be processed on farm. Skipping")
            return

        # TODO (antirotor): Find better name for the key  # noqa: FIX002, TD003
        if not instance.data.get("representations_with_traits"):
            self.log.debug(
                "Instance has no representations with traits. Skipping")
            return

        # 2) filter representations based on LifeCycle traits
        instance.data["representations_with_traits"] = self.filter_lifecycle(
            instance.data["representations_with_traits"]
        )

        representations = instance.data["representations_with_traits"]
        if not representations:
            self.log.debug(
                "Instance has no persistent representations. Skipping")
            return

        # template_name = self.get_template_name(instance)

    @staticmethod
    def filter_lifecycle(
            representations: list[Representation]) -> list[Representation]:
        """Filter representations based on LifeCycle traits.

        Args:
            representations (list): List of representations.

        Returns:
            list: Filtered representations.

        """
        return [
            representation
            for representation in representations
            if representation.contains_trait(Persistent)
        ]

    def get_template_name(self, instance: pyblish.api.Instance) -> str:
        """Return anatomy template name to use for integration.

        Args:
            instance (pyblish.api.Instance): Instance to process.

        Returns:
            str: Anatomy template name

        """
        # Anatomy data is pre-filled by Collectors
        context = instance.context
        project_name = context.data["projectName"]

        # Task can be optional in anatomy data
        host_name = context.data["hostName"]
        anatomy_data = instance.data["anatomyData"]
        product_type = instance.data["productType"]
        task_info = anatomy_data.get("task") or {}

        return get_publish_template_name(
            project_name,
            host_name,
            product_type,
            task_name=task_info.get("name"),
            task_type=task_info.get("type"),
            project_settings=context.data["project_settings"],
            logger=self.log
        )
