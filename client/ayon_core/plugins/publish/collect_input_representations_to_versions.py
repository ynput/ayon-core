import ayon_api
import ayon_api.utils
import pyblish.api

from ayon_core.pipeline.publish.input_versions import InputVersion


class CollectInputRepresentationsToVersions(pyblish.api.ContextPlugin):
    """Converts collected input representations to input versions.

    Any data in `instance.data["inputRepresentations"]` gets converted into
    `instance.data["inputVersions"]` as supported in OpenPype.

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
            fields={"id", "versionId"})

        version_info_by_repre_id = {
            repre["id"]: InputVersion(version_id=repre["versionId"])
            for repre in repre_entities
        }

        # Replace hero versions with their real versions
        version_info_by_repre_id = self.hero_versions_to_versions(
            version_info_by_repre_id,
            project_name,
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

    def hero_versions_to_versions(
            self,
            version_info_by_repre_id: dict[str, InputVersion],
            project_name: str,
    ) -> dict[str, InputVersion]:
        """Remap hero versions to their 'real' version ids"""
        # Get all hero version ids among the versions
        hero_versions: list[dict] = list(ayon_api.get_hero_versions(
            project_name=project_name,
            version_ids={
                v.version_id for v in version_info_by_repre_id.values()
            },
            fields={"id", "productId"},
        ))
        if not hero_versions:
            return version_info_by_repre_id

        product_ids = {hv["productId"] for hv in hero_versions}
        hero_version_ids: set[str] = {hv["id"] for hv in hero_versions}

        # TODO: When backend supports it filter directly to only versions
        #  where hero version id matches our list of versions or skip those
        #  that have no hero version id
        versions = ayon_api.get_versions(
            project_name,
            product_ids=product_ids,
            fields={"id", "heroVersionId"}
        )
        # Mapping from hero version id to real version id
        version_id_by_hero_version_id: dict[str, str] = {
            v["heroVersionId"]: v["id"] for v in versions
            # Disregard versions with irrelevant hero version id
            if v["heroVersionId"] in hero_version_ids
        }
        self.log.debug(
            f"Hero version to version id map: {version_id_by_hero_version_id}"
        )

        # Update mapping to point to real version id
        for repre_id, input_version in tuple(
            version_info_by_repre_id.items()
        ):
            # Nothing to remap if not a hero version
            if input_version.version_id not in hero_version_ids:
                continue

            # Get real version id for hero version id
            hero_version_id: str = input_version.version_id
            real_version_id: str = version_id_by_hero_version_id.get(
                hero_version_id
            )
            if not real_version_id:
                self.log.debug(
                    "Could not find real version for hero version: %s.",
                    hero_version_id,
                )
                continue

            version_info_by_repre_id[repre_id] = (
                InputVersion(
                    version_id=real_version_id,
                    hero=True,
                    hero_version_id=hero_version_id,
                )
            )

        return version_info_by_repre_id
