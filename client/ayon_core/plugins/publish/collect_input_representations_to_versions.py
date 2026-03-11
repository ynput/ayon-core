import ayon_api
import ayon_api.utils
import pyblish.api

from ayon_core.pipeline.publish.input_versions import (
    version_ids_to_input_versions
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
        representations = set()
        for instance in context:
            inst_repre = instance.data.get("inputRepresentations", [])
            if inst_repre:
                representations.update(inst_repre)

        # Ignore representation ids that are not valid
        representations = {
            representation_id for representation_id in representations
            if ayon_api.utils.convert_entity_id(representation_id)
        }
        project_name: str = context.data["projectName"]
        repre_entities = ayon_api.get_representations(
            project_name=project_name,
            representation_ids=representations,
            fields={"id", "versionId"}
        )

        # Get version input link info for the version ids
        version_info_by_version_id = version_ids_to_input_versions(
            project_name=project_name,
            version_ids={repre["versionId"] for repre in repre_entities},
            log=self.log
        )
        version_info_by_repre_id = {}
        for repre in repre_entities:
            version_id: str = repre["versionId"]
            version_info_by_repre_id[repre["id"]] = (
                version_info_by_version_id.get(version_id)
            )

        for instance in context:
            inst_repre = instance.data.get("inputRepresentations", [])
            if not inst_repre:
                continue

            input_versions = instance.data.setdefault("inputVersions", [])
            for repre_id in inst_repre:
                version_id = version_info_by_repre_id.get(repre_id)
                if version_id:
                    input_versions.append(version_id)
                else:
                    self.log.debug(
                        "Representation id {} skipped because its version is "
                        "not found in current project. Likely it is loaded "
                        "from a library project or uses a deleted "
                        "representation or version.".format(repre_id)
                    )
