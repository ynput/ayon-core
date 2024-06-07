import pyblish.api

from ayon_core.pipeline import (
    PublishXmlValidationError,
    OptionalPyblishPluginMixin
)


class ValidateDeadlinePools(OptionalPyblishPluginMixin,
                            pyblish.api.InstancePlugin):
    """Validate primaryPool and secondaryPool on instance.

    Values are on instance based on value insertion when Creating instance or
    by Settings in CollectDeadlinePools.
    """

    label = "Validate Deadline Pools"
    order = pyblish.api.ValidatorOrder
    families = ["rendering",
                "render.farm",
                "render.frames_farm",
                "renderFarm",
                "renderlayer",
                "maxrender",
                "publish.hou"]
    optional = True

    # cache
    pools_per_url = {}

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        if not instance.data.get("farm"):
            self.log.debug("Skipping local instance.")
            return

        deadline_url = instance.data["deadline"]["url"]
        addons_manager = instance.context.data["ayonAddonsManager"]
        deadline_addon = addons_manager["deadline"]
        pools = self.get_pools(
            deadline_addon,
            deadline_url,
            instance.data["deadline"].get("auth")
        )

        invalid_pools = {}
        primary_pool = instance.data.get("primaryPool")
        if primary_pool and primary_pool not in pools:
            invalid_pools["primary"] = primary_pool

        secondary_pool = instance.data.get("secondaryPool")
        if secondary_pool and secondary_pool not in pools:
            invalid_pools["secondary"] = secondary_pool

        if invalid_pools:
            message = "\n".join(
                "{} pool '{}' not available on Deadline".format(key.title(),
                                                                pool)
                for key, pool in invalid_pools.items()
            )
            raise PublishXmlValidationError(
                plugin=self,
                message=message,
                formatting_data={"pools_str": ", ".join(pools)}
            )

    def get_pools(self, deadline_addon, deadline_url, auth):
        if deadline_url not in self.pools_per_url:
            self.log.debug(
                "Querying available pools for Deadline url: {}".format(
                    deadline_url)
            )
            pools = deadline_addon.get_deadline_pools(
                deadline_url, auth=auth, log=self.log
            )
            # some DL return "none" as a pool name
            if "none" not in pools:
                pools.append("none")
            self.log.info("Available pools: {}".format(pools))
            self.pools_per_url[deadline_url] = pools

        return self.pools_per_url[deadline_url]
