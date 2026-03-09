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

        representation_id_to_version_id = {
            repre["id"]: InputVersion(version_id=repre["versionId"])
            for repre in repre_entities
        }

        # Remap hero versions to their 'real' version ids
        hero_versions = list(ayon_api.get_hero_versions(
            project_name=project_name,
            version_ids={
                v.version_id for v in representation_id_to_version_id.values()
            },
            fields={"id", "productId", "version"}
        ))
        # Replace hero versions with their real versions
        representation_id_to_version_id = self.hero_versions_to_versions(
            representation_id_to_version_id,
            hero_versions,
            project_name,
        )

        for instance in context:
            inst_repre = instance.data.get("inputRepresentations", [])
            if not inst_repre:
                continue

            input_versions = instance.data.setdefault("inputVersions", [])
            for repre_id in inst_repre:
                version_id = representation_id_to_version_id.get(repre_id)
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
            representation_id_to_version_id: dict[str, InputVersion],
            hero_versions: list[dict],
            project_name: str,
    ) -> dict[str, InputVersion]:
        if not hero_versions:
            return representation_id_to_version_id

        product_ids = {hv["productId"] for hv in hero_versions}
        versions = ayon_api.get_versions(
            project_name,
            product_ids=product_ids
        )
        version_id_by_product_id_and_version: dict[tuple[str, int], str] = {
            (v["productId"], v["version"]): v["id"] for v in versions
        }

        for hero_version in hero_versions:
            real_key: tuple[str, int] = (
                hero_version["productId"],
                # Hero version uses negative version numbers of
                # their real versions
                abs(hero_version["version"])
            )
            real_version_id = version_id_by_product_id_and_version.get(
                real_key)
            if not real_version_id:
                self.log.debug(
                    "Could not find real version for hero version: %s.",
                    hero_version["id"],
                )
                continue

            # Update mapping to point to real version id
            for repre_id, input_version in tuple(
                representation_id_to_version_id.items()
            ):
                if input_version.version_id == hero_version["id"]:
                    representation_id_to_version_id[repre_id] = (
                        InputVersion(
                            version_id=real_version_id,
                            hero=True,
                            hero_version_id=hero_version["id"],
                        )
                    )

        return representation_id_to_version_id
