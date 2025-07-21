import ayon_api
import ayon_api.utils

from ayon_core.pipeline import registered_host
import pyblish.api


class CollectSceneLoadedVersions(pyblish.api.ContextPlugin):

    order = pyblish.api.CollectorOrder + 0.0001
    label = "Collect Versions Loaded in Scene"
    hosts = [
        "aftereffects",
        "blender",
        "celaction",
        "fusion",
        "harmony",
        "hiero",
        "houdini",
        "maya",
        "nuke",
        "photoshop",
        "resolve",
        "tvpaint"
    ]

    def process(self, context):
        host = registered_host()
        if host is None:
            self.log.warn("No registered host.")
            return

        if not hasattr(host, "ls"):
            host_name = host.__name__
            self.log.warn("Host %r doesn't have ls() implemented." % host_name)
            return

        loaded_versions = []
        containers = list(host.ls())
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

        context.data["loadedVersions"] = loaded_versions
