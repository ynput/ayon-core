import collections
from typing import Any
import dataclasses

import pyblish.api

import ayon_api
from ayon_core.pipeline.publish.input_versions import InputVersion


@dataclasses.dataclass
class LinkPayload:
    input_id: str
    output_id: str
    data: dict[str, Any]


LinksByType = dict[str, list[LinkPayload]]


def create_link(
    project_name: str,
    link_type_name: str,
    input_id: str,
    input_type: str,
    output_id: str,
    output_type: str,
    data: dict,
):
    """Create link in AYON.

    TODO Replace with 'ayon_api.create_link' when AYON launcher >= 1.5.2
        is required by ayon-core.

    """
    full_link_type_name = ayon_api.get_full_link_type_name(
        link_type_name, input_type, output_type)

    kwargs = {
        "input": input_id,
        "output": output_id,
        "linkType": full_link_type_name,
    }
    if data:
        kwargs["data"] = data

    response = ayon_api.post(
        f"projects/{project_name}/links", **kwargs
    )
    response.raise_for_status()


class IntegrateInputLinksAYON(pyblish.api.ContextPlugin):
    """Connecting version level dependency links

    Handles links:
        - generative - what gets produced from workfile
        - reference - what was loaded into workfile

    It expects workfile instance is being published.
    """

    order = pyblish.api.IntegratorOrder + 0.2
    label = "Connect Dependency InputLinks AYON"

    def process(self, context: pyblish.api.Context):
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
        new_links_by_type: LinksByType = collections.defaultdict(list)

        self.create_workfile_links(
            workfile_instance, other_instances, new_links_by_type)

        self.create_generative_links(other_instances, new_links_by_type)

        self.create_links_on_server(context, new_links_by_type)

    def split_instances(self, context: pyblish.api.Context):
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

            product_base_type = instance.data.get("productBaseType")
            if not product_base_type:
                product_base_type = instance.data["productType"]

            if product_base_type == "workfile":
                workfile_instance = instance
            else:
                other_instances.append(instance)
        return workfile_instance, other_instances

    def add_link(
        self,
        new_links_by_type: LinksByType,
        link_type: str,
        input_id: str,
        output_id: str,
        data: dict[str, Any],
    ):
        """Add dependency link data into temporary variable.

        Args:
            new_links_by_type (
                dict[str, list[tuple[str, str, Optional[dict[str, Any]]]]]
            ): Object where output is stored.
            link_type (str): Type of link, one of 'reference' or 'generative'
            input_id (str): Input version id.
            output_id (str): Output version id.
            data (dict[str, Any]): Link metadata.
        """
        new_links_by_type[link_type].append(
            LinkPayload(
                input_id=input_id,
                output_id=output_id,
                data=data
            )
        )

    def create_workfile_links(
        self,
        workfile_instance: pyblish.api.Instance,
        other_instances: list[pyblish.api.Instance],
        new_links_by_type: LinksByType,
    ):
        """Adds links (generative and reference) for workfile.

        Args:
            workfile_instance (pyblish.plugin.Instance): Published workfile.
            other_instances (list[pyblish.plugin.Instance]): Other published
                instances
            new_links_by_type (LinksByType): Dictionary collecting new created
                links by its type.
        """
        if workfile_instance is None:
            self.log.debug("No workfile in this publish session.")
            return

        workfile_version_id = workfile_instance.data["versionEntity"]["id"]
        # link workfile to all publishing versions
        for instance in other_instances:
            self.add_link(
                new_links_by_type,
                link_type="generative",
                input_id=workfile_version_id,
                output_id=instance.data["versionEntity"]["id"],
                data={}
            )

        loaded_versions = workfile_instance.context.data.get("loadedVersions")
        if not loaded_versions:
            return

        # link all loaded versions in scene into workfile
        for input_version in loaded_versions:
            input_version = InputVersion.from_value(input_version)
            self.add_link(
                new_links_by_type,
                link_type="reference",
                input_id=input_version.version_id,
                output_id=workfile_version_id,
                data=input_version.data
            )

    def create_generative_links(
        self,
        other_instances: list[pyblish.api.Instance],
        new_links_by_type: LinksByType,
    ):
        for instance in other_instances:
            input_versions = instance.data.get("inputVersions")
            if not input_versions:
                continue

            version_entity = instance.data["versionEntity"]
            for input_version in input_versions:
                input_version = InputVersion.from_value(input_version)
                self.add_link(
                    new_links_by_type,
                    link_type="generative",
                    input_id=input_version.version_id,
                    output_id=version_entity["id"],
                    data=input_version.data,
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

        existing_in_links = ayon_api.get_versions_links(
            project_name, entity_ids, [link_type], "out"
        )

        for entity_id, links in existing_in_links.items():
            if not links:
                continue
            for link in links:
                output[entity_id].add(link["entityId"])
        return output

    def create_links_on_server(
        self,
        context: pyblish.api.Context,
        new_links: LinksByType,
    ):
        """Create new links on server."""
        if not new_links:
            return

        project_name: str = context.data["projectName"]

        # Make sure link types are available on server
        for link_type in new_links.keys():
            ayon_api.make_sure_link_type_exists(
                project_name, link_type, "version", "version"
            )

        # Create link themselves
        for link_type, link_payloads in new_links.items():
            # Make sure there are no duplicates of src > dst ids and merge
            # metadata if multiple links are found.
            mapping: dict[tuple[str, str], dict] = collections.defaultdict(
                dict
            )
            for link_payload in link_payloads:
                connection = (link_payload.input_id, link_payload.output_id)
                mapping[connection].update(link_payload.data)

            in_ids = {payload.input_id for payload in link_payloads}
            existing_links_by_in_id = self._get_existing_links(
                project_name, link_type, in_ids
            )

            for (input_id, output_id), data in mapping.items():
                existing_links = existing_links_by_in_id[input_id]
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
                    "version",
                    data=data,
                )
