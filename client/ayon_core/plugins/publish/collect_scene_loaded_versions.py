from __future__ import annotations
from typing import Any
import ayon_api
import ayon_api.utils

from ayon_core.host import ILoadHost
from ayon_core.pipeline import registered_host

import pyblish.api


class CollectSceneLoadedVersions(pyblish.api.ContextPlugin):

    order = pyblish.api.CollectorOrder + 0.0001
    label = "Collect Versions Loaded in Scene"

    def process(self, context):
        host = registered_host()
        if host is None:
            self.log.warning("No registered host.")
            return

        if not isinstance(host, ILoadHost):
            host_name = host.name
            self.log.warning(
                f"Host {host_name} does not implement ILoadHost. "
                "Skipping querying of loaded versions in scene."
            )
            return

        containers = list(host.get_containers())
        if not containers:
            # Opt out early if there are no containers
            self.log.debug("No loaded containers found in scene.")
            return

        containers = self._filter_invalid_containers(containers)

        repre_ids = {
            container["representation"]
            for container in containers
        }

        # Ignore representation ids that are not valid
        repre_ids = {
            representation_id for representation_id in repre_ids
            if ayon_api.utils.convert_entity_id(representation_id)
        }

        project_name = context.data["projectName"]
        repre_entities = ayon_api.get_representations(
            project_name,
            representation_ids=repre_ids,
            fields={"id", "versionId"}
        )
        repre_entities_by_id = {
            repre_entity["id"]: repre_entity
            for repre_entity in repre_entities
        }

        # QUESTION should we add same representation id when loaded multiple
        #   times?
        loaded_versions = []
        for con in containers:
            repre_id = con["representation"]
            repre_entity = repre_entities_by_id.get(repre_id)
            if repre_entity is None:
                self.log.warning((
                    "Skipping container,"
                    " did not find representation document. {}"
                ).format(str(con)))
                continue

            # NOTE:
            # may have more than one representation that are same version
            version = {
                "container_name": con["name"],
                "representation_id": repre_entity["id"],
                "version_id": repre_entity["versionId"],
            }
            loaded_versions.append(version)

        self.log.debug(f"Collected {len(loaded_versions)} loaded versions.")
        context.data["loadedVersions"] = loaded_versions

    def _filter_invalid_containers(
        self,
        containers: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Filter out invalid containers lacking required keys.

        Skip any invalid containers that lack 'representation' or 'name'
        keys to avoid KeyError.
        """
        # Only filter by what's required for this plug-in instead of validating
        # a full container schema.
        required_keys = {"name", "representation"}
        valid = []
        for container in containers:
            missing = [key for key in required_keys if key not in container]
            if missing:
                self.log.debug(
                    "Skipping invalid container, missing required keys:"
                    " {}. {}".format(", ".join(missing), container)
                )
                continue
            valid.append(container)

        return valid
