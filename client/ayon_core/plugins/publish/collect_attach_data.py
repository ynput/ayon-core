import copy

import pyblish.api


class CollectAttachData(pyblish.api.ContextPlugin):
    """Collect version metadata from attached reviewables."""

    order = pyblish.api.CollectorOrder + 0.491
    label = "Collect data from attached products"

    def process(self, context):
        self.log.debug("Collecting data from attached products")
        for instance in context:
            if not instance.data.get("active", True):
                continue

            attach_to = self._get_attach_targets(instance)
            if not attach_to:
                continue

            attach_instance = self._get_source_attach_instance(
                instance, attach_to
            )
            if attach_instance is None:
                continue

            self._merge_attached_data(attach_instance, instance)

    def _get_attach_targets(self, instance):
        publish_attributes = instance.data.get("publish_attributes", {})
        attach_reviewables = publish_attributes.get("AttachReviewables", {})
        attach_to = attach_reviewables.get("attach")
        if not attach_to:
            return []
        return attach_to

    def _get_attach_instances(self, instance, attach_to):
        attach_instances = []
        for attach_instance_id in attach_to:
            attach_instance = next(
                (
                    _inst
                    for _inst in instance.context
                    if _inst.data.get("instance_id") == attach_instance_id
                ),
                None,
            )
            if attach_instance is None:
                self.log.debug(
                    "Attached instance id '%s' was not found in context.",
                    attach_instance_id,
                )
                continue

            if not attach_instance.data.get("active", True):
                self.log.debug(
                    "Skipping inactive attached instance '%s'.",
                    attach_instance.name,
                )
                continue

            if attach_instance.data.get("farm"):
                self.log.warning(
                    "Attaching data to farm instances is not supported yet."
                )
                continue

            attach_instances.append(attach_instance)
        return attach_instances

    def _get_source_attach_instance(self, instance, attach_to):
        attach_instances = self._get_attach_instances(instance, attach_to)
        if not attach_instances:
            return None

        if len(attach_instances) > 1:
            self.log.debug(
                "Multiple attached instances found for '%s'. Using '%s'.",
                instance.name,
                attach_instances[0].name,
            )

        return attach_instances[0]

    def _merge_attached_data(self, attached_instance, receiver_instance):
        attached_version = attached_instance.data.get("version")
        attached_version_data = copy.deepcopy(
            attached_instance.data.get("versionData") or {}
        )
        if attached_version is None and not attached_version_data:
            self.log.debug(
                "No attached version metadata found on '%s'.",
                attached_instance.name,
            )
            return

        self.log.debug(
            "Previous data on receiver instance '%s': %s",
            receiver_instance.name,
            receiver_instance.data,
        )

        if attached_version is not None:
            receiver_instance.data["version"] = copy.deepcopy(attached_version)
            anatomy_data = receiver_instance.data.get("anatomyData")
            if anatomy_data is not None:
                anatomy_data["version"] = copy.deepcopy(attached_version)

        if attached_version_data:
            receiver_instance.data.setdefault("versionData", {}).update(
                copy.deepcopy(attached_version_data)
            )

        self.log.debug(
            "Merged attached metadata from '%s' to '%s': version=%s, "
            "versionData=%s",
            attached_instance.name,
            receiver_instance.name,
            receiver_instance.data.get("version"),
            receiver_instance.data.get("versionData"),
        )
        self.log.debug(
            "Updated data on receiver instance '%s': %s",
            receiver_instance.name,
            receiver_instance.data,
        )
