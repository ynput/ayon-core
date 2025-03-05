import copy
import pyblish.api
from typing import List

from ayon_core.lib import EnumDef
from ayon_core.pipeline import OptionalPyblishPluginMixin


class AttachReviewables(
    pyblish.api.InstancePlugin, OptionalPyblishPluginMixin
):
    """Attach reviewable to other instances

    This pre-integrator plugin allows instances to be 'attached to' other
    instances by moving all its representations over to the other instance.
    Even though this technically could work for any representation the current
    intent is to use for reviewables only, like e.g. `review` or `render`
    product type.

    When the reviewable is attached to another instance, the instance itself
    will not be published as a separate entity. Instead, the representations
    will be copied/moved to the instances it is attached to.
    """

    families = ["render", "review"]
    order = pyblish.api.IntegratorOrder - 0.499
    label = "Attach reviewables"

    def process(self, instance):
        # TODO: Support farm.
        #  If instance is being submitted to the farm we should pass through
        #  the 'attached reviewables' metadata to the farm job
        # TODO: Reviewable frame range and resolutions
        #  Because we are attaching the data to another instance, how do we
        #  correctly propagate the resolution + frame rate to the other
        #  instance? Do we even need to?
        # TODO: If this were to attach 'renders' to another instance that would
        #  mean there wouldn't necessarily be a render publish separate as a
        #  result. Is that correct expected behavior?
        attr_values = self.get_attr_values_from_data(instance.data)
        attach_to = attr_values.get("attach", [])
        if not attach_to:
            self.log.debug(
                "Reviewable is not set to attach to another instance."
            )
            return

        attach_instances: List[pyblish.api.Instance] = []
        for attach_instance_id in attach_to:
            # Find the `pyblish.api.Instance` matching the `CreatedInstance.id`
            # in the `attach_to` list
            attach_instance = next(
                (
                    _inst
                    for _inst in instance.context
                    if _inst.data.get("instance_id") == attach_instance_id
                ),
                None,
            )
            if attach_instance is None:
                continue

            # Skip inactive instances
            if not attach_instance.data.get("active", True):
                continue

            attach_instances.append(attach_instance)

        self.log.info(
            f"Attaching reviewable to other instances: {attach_instances}"
        )

        # Copy the representations of this reviewable instance to the other
        # instance
        representations = instance.data.get("representations", [])
        for attach_instance in attach_instances:
            self.log.info(f"Attaching to {attach_instance.name}")
            attach_instance.data.setdefault("representations", []).extend(
                copy.deepcopy(representations)
            )

        # Delete representations on the reviewable instance itself
        for repre in representations:
            self.log.debug(
                "Marking representation as deleted because it was "
                f"attached to other instances instead: {repre}"
            )
            repre.setdefault("tags", []).append("delete")

        # Stop integrator from trying to integrate this instance
        if attach_to:
            instance.data["integrate"] = False

    @classmethod
    def get_attr_defs_for_instance(cls, create_context, instance):
        # TODO: Check if instance is actually a 'reviewable'
        # Filtering of instance, if needed, can be customized
        if not cls.instance_matches_plugin_families(instance):
            return []

        items = []
        for other_instance in create_context.instances:
            if other_instance == instance:
                continue

            # Do not allow attaching to other reviewable instances
            if other_instance.data["productType"] in cls.families:
                continue

            items.append(
                {
                    "label": other_instance.label,
                    "value": str(other_instance.id),
                }
            )

        return [
            EnumDef(
                "attach",
                label="Attach reviewable",
                multiselection=True,
                items=items,
                tooltip="Attach this reviewable to another instance",
            )
        ]
