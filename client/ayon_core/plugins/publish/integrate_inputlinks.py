import collections

import pyblish.api
from ayon_api import (
    create_link,
    make_sure_link_type_exists,
    get_versions_links,
)


class IntegrateInputLinksAYON(pyblish.api.ContextPlugin):
    """Connecting version level dependency links

    Handles links:
        - generative - what gets produced from workfile
        - reference - what was loaded into workfile

    It expects workfile instance is being published.
    """

    order = pyblish.api.IntegratorOrder + 0.2
    label = "Connect Dependency InputLinks AYON"

    def process(self, context):
        """Connect dependency links for all instances, globally

        Code steps:
        - filter instances that integrated version
            - have "versionEntity" entry in data
        - separate workfile instance within filtered instances
        - when workfile instance is available:
            - link all `loadedVersions` as input of the workfile
            - link workfile as input of all other integrated versions
        - link version's inputs if it's instance have "inputVersions" entry
        -

        inputVersions:
            The "inputVersions" in instance.data should be a list of
            version ids (str), which are the dependencies of the publishing
            instance that should be extracted from working scene by the DCC
            specific publish plugin.
        """

        workfile_instance, other_instances = self.split_instances(context)

        # Variable where links are stored in submethods
        new_links_by_type = collections.defaultdict(list)

        self.create_workfile_links(
            workfile_instance, other_instances, new_links_by_type)

        self.create_generative_links(other_instances, new_links_by_type)

        self.create_links_on_server(context, new_links_by_type)

    def split_instances(self, context):
        """Separates published instances into workfile and other

        Returns:
            (tuple(pyblish.plugin.Instance), list(pyblish.plugin.Instance))
        """
        workfile_instance = None
        other_instances = []

        for instance in context:
            # Skip inactive instances
            if not instance.data.get("publish", True):
                continue

            if not instance.data.get("versionEntity"):
                self.log.debug(
                    "Instance {} doesn't have version.".format(instance))
                continue

            product_type = instance.data["productType"]
            if product_type == "workfile":
                workfile_instance = instance
            else:
                other_instances.append(instance)
        return workfile_instance, other_instances

    def add_link(self, new_links_by_type, link_type, input_id, output_id):
        """Add dependency link data into temporary variable.

        Args:
            new_links_by_type (dict[str, list[dict[str, Any]]]): Object where
                output is stored.
            link_type (str): Type of link, one of 'reference' or 'generative'
            input_id (str): Input version id.
            output_id (str): Output version id.
        """

        new_links_by_type[link_type].append((input_id, output_id))

    def create_workfile_links(
        self, workfile_instance, other_instances, new_links_by_type
    ):
        """Adds links (generative and reference) for workfile.

        Args:
            workfile_instance (pyblish.plugin.Instance): published workfile
            other_instances (list[pyblish.plugin.Instance]): other published
                instances
            new_links_by_type (dict[str, list[str]]): dictionary collecting new
                created links by its type
        """
        if workfile_instance is None:
            self.log.warn("No workfile in this publish session.")
            return

        workfile_version_id = workfile_instance.data["versionEntity"]["id"]
        # link workfile to all publishing versions
        for instance in other_instances:
            self.add_link(
                new_links_by_type,
                "generative",
                workfile_version_id,
                instance.data["versionEntity"]["id"],
            )

        loaded_versions = workfile_instance.context.data.get("loadedVersions")
        if not loaded_versions:
            return

        # link all loaded versions in scene into workfile
        for version in loaded_versions:
            self.add_link(
                new_links_by_type,
                "reference",
                version["version_id"],
                workfile_version_id,
            )

    def create_generative_links(self, other_instances, new_links_by_type):
        for instance in other_instances:
            input_versions = instance.data.get("inputVersions")
            if not input_versions:
                continue

            version_entity = instance.data["versionEntity"]
            for input_version in input_versions:
                self.add_link(
                    new_links_by_type,
                    "generative",
                    input_version,
                    version_entity["id"],
                )

    def _get_existing_links(self, project_name, link_type, entity_ids):
        """Find all existing links for given version ids.

        Args:
            project_name (str): Name of project.
            link_type (str): Type of link.
            entity_ids (set[str]): Set of version ids.

        Returns:
            dict[str, set[str]]: Existing links by version id.
        """

        output = collections.defaultdict(set)
        if not entity_ids:
            return output

        existing_in_links = get_versions_links(
            project_name, entity_ids, [link_type], "output"
        )

        for entity_id, links in existing_in_links.items():
            if not links:
                continue
            for link in links:
                output[entity_id].add(link["entityId"])
        return output

    def create_links_on_server(self, context, new_links):
        """Create new links on server.

        Args:
            dict[str, list[tuple[str, str]]]: Version links by link type.
        """

        if not new_links:
            return

        project_name = context.data["projectName"]

        # Make sure link types are available on server
        for link_type in new_links.keys():
            make_sure_link_type_exists(
                project_name, link_type, "version", "version"
            )

        # Create link themselves
        for link_type, items in new_links.items():
            mapping = collections.defaultdict(set)
            # Make sure there are no duplicates of src > dst ids
            for item in items:
                _input_id, _output_id = item
                mapping[_input_id].add(_output_id)

            existing_links_by_in_id = self._get_existing_links(
                project_name, link_type, set(mapping.keys())
            )

            for input_id, output_ids in mapping.items():
                existing_links = existing_links_by_in_id[input_id]
                for output_id in output_ids:
                    # Skip creation of link if already exists
                    # NOTE: AYON server does not support
                    #     to have same links
                    if output_id in existing_links:
                        continue
                    create_link(
                        project_name,
                        link_type,
                        input_id,
                        "version",
                        output_id,
                        "version"
                    )
