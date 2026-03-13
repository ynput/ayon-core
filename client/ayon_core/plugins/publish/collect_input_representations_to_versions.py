from __future__ import annotations
from typing import Optional

import ayon_api
import ayon_api.utils
import pyblish.api

from ayon_core.pipeline.publish.input_versions import (
    version_ids_to_input_versions,
    InputVersion
)


class CollectInputRepresentationsToVersions(pyblish.api.ContextPlugin):
    """Converts collected input representations to input versions.

    Any data in `instance.data["inputRepresentations"]` gets converted into
    `instance.data["inputVersions"]` as supported in AYON.

    """
    # This is a ContextPlugin because then we can query the database only once
    # for the conversion of representation ids to version ids (optimization)
    label = "Input Representations to Versions"
    order = pyblish.api.CollectorOrder + 0.499
    hosts = ["*"]

    def process(self, context: pyblish.api.Context):
        # Query all version ids for representation ids from the database once
        representation_ids: set[str] = set()
        for instance in context:
            inst_repre = instance.data.get("inputRepresentations", [])
            if inst_repre:
                representation_ids.update(inst_repre)

        # Ignore representation ids that are not valid
        representation_ids = {
            representation_id for representation_id in representation_ids
            if ayon_api.utils.convert_entity_id(representation_id)
        }
        project_name: str = context.data["projectName"]
        repre_entities: list[dict[str, str]] = list(
            ayon_api.get_representations(
                project_name=project_name,
                representation_ids=representation_ids,
                fields={"id", "versionId"}
            )
        )

        # Get version input link info for the version ids
        version_info_by_version_id = version_ids_to_input_versions(
            project_name=project_name,
            version_ids={repre["versionId"] for repre in repre_entities},
            log=self.log
        )
        version_info_by_repre_id: dict[str, Optional[InputVersion]] = {}
        for repre in repre_entities:
            version_id: str = repre["versionId"]
            version_info_by_repre_id[repre["id"]] = (
                version_info_by_version_id.get(version_id)
            )

        for instance in context:
            inst_repre_ids: list[str] = instance.data.get(
                "inputRepresentations", []
            )
            if not inst_repre_ids:
                continue

            input_versions: list[InputVersion] = instance.data.setdefault(
                "inputVersions", []
            )
            for repre_id in inst_repre_ids:
                version_info = version_info_by_repre_id.get(repre_id)
                if version_info:
                    input_versions.append(version_info)
                else:
                    self.log.debug(
                        "Representation id {} skipped because its version is "
                        "not found in current project. Likely it is loaded "
                        "from a library project or uses a deleted "
                        "representation or version.".format(repre_id)
                    )
