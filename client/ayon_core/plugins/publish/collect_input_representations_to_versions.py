import ayon_api
import ayon_api.utils
import pyblish.api


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

    def process(self, context):
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

        repre_entities = ayon_api.get_representations(
            project_name=context.data["projectName"],
            representation_ids=representations,
            fields={"id", "versionId"})

        representation_id_to_version_id = {
            repre["id"]: repre["versionId"]
            for repre in repre_entities
        }

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
