""" Integrate Thumbnails for use in Loaders.

    This thumbnail is different from 'thumbnail' representation which could
    be uploaded to Ftrack, or used as any other representation in Loaders to
    pull into a scene.

    This one is used only as image describing content of published item and
        shows up only in Loader or WebUI.

    Instance must have 'published_representations' to
        be able to integrate thumbnail.
    Possible sources of thumbnail paths:
    - instance.data["thumbnailPath"]
    - representation with 'thumbnail' name in 'published_representations'
    - context.data["thumbnailPath"]

    Notes:
        Issue with 'thumbnail' representation is that we most likely don't
            want to integrate it as representation. Integrated representation
            is polluting Loader and database without real usage. That's why
            they usually have 'delete' tag to skip the integration.

"""

import os
import collections
import time

import ayon_api
from ayon_api.operations import OperationsSession
import pyblish.api

from ayon_core.lib import format_file_size
from ayon_core.pipeline.publish import PublishXmlValidationError

from ayon_core import __version__


InstanceFilterResult = collections.namedtuple(
    "InstanceFilterResult",
    ["instance", "thumbnail_path", "version_id"]
)


class IntegrateThumbnailsAYON(pyblish.api.ContextPlugin):
    """Integrate Thumbnails for use in Loaders."""

    label = "Integrate Thumbnails to AYON"
    order = pyblish.api.IntegratorOrder + 0.01

    def process(self, context):
        # Filter instances which can be used for integration
        filtered_instance_items = self._prepare_instances(context)
        if not filtered_instance_items:
            self.log.debug(
                "All instances were filtered. Thumbnail integration skipped."
            )
            return

        project_name = context.data["projectName"]

        # Collect version ids from all filtered instance
        version_ids = {
            instance_items.version_id
            for instance_items in filtered_instance_items
        }
        # Query versions
        version_entities = ayon_api.get_versions(
            project_name,
            version_ids=version_ids,
            hero=True,
            fields={"id", "version"}
        )
        # Store version by their id (converted to string)
        version_entities_by_id = {
            version_entity["id"]: version_entity
            for version_entity in version_entities
        }
        self._integrate_thumbnails(
            filtered_instance_items,
            version_entities_by_id,
            project_name
        )

    def _prepare_instances(self, context):
        context_thumbnail_path = context.data.get("thumbnailPath")
        valid_context_thumbnail = bool(
            context_thumbnail_path
            and os.path.exists(context_thumbnail_path)
        )

        filtered_instances = []
        anatomy = context.data["anatomy"]
        for instance in context:
            instance_label = self._get_instance_label(instance)
            # Skip instances without published representations
            # - there is no place where to put the thumbnail
            published_repres = instance.data.get("published_representations")
            if not published_repres:
                self.log.debug(
                    "There are no published representations"
                    f" on the instance {instance_label}."
                )
                continue

            # Find thumbnail path on instance
            thumbnail_path = (
                instance.data.get("thumbnailPath")
                or self._get_instance_thumbnail_path(
                    published_repres, anatomy
                )
            )
            if thumbnail_path:
                self.log.debug(
                    f"Found thumbnail path for instance \"{instance_label}\"."
                    " Thumbnail path: {}"
                )

            elif valid_context_thumbnail:
                # Use context thumbnail path if is available
                thumbnail_path = context_thumbnail_path
                self.log.debug(
                    "Using context thumbnail path for instance"
                    f" \"{instance_label}\". Thumbnail path: {thumbnail_path}"
                )

            # Skip instance if thumbnail path is not available for it
            if not thumbnail_path:
                self.log.debug((
                    f"Skipping thumbnail integration for instance"
                    f" \"{instance_label}\". Instance and context"
                    " thumbnail paths are not available."
                ).format(instance_label))
                continue

            version_id = str(self._get_version_id(published_repres))
            filtered_instances.append(
                InstanceFilterResult(instance, thumbnail_path, version_id)
            )
        return filtered_instances

    def _get_version_id(self, published_representations):
        for repre_info in published_representations.values():
            return repre_info["representation"]["versionId"]

    def _get_instance_thumbnail_path(
        self, published_representations, anatomy
    ):
        thumb_repre_entity = None
        for repre_info in published_representations.values():
            repre_entity = repre_info["representation"]
            if "thumbnail" in repre_entity["name"].lower():
                thumb_repre_entity = repre_entity
                break

        if thumb_repre_entity is None:
            self.log.debug(
                "There is no representation with name \"thumbnail\""
            )
            return None

        path = thumb_repre_entity["attrib"]["path"]
        filled_path = anatomy.fill_root(path)
        if not os.path.exists(filled_path):
            self.log.warning(
                f"Thumbnail file cannot be found. Path: {filled_path}"
            )
            return None
        return os.path.normpath(filled_path)

    def _create_thumbnail(self, project_name: str, src_filepath: str) -> str:
        """Upload thumbnail to AYON and return its id."""
        size = os.path.getsize(src_filepath)
        self.log.info(
            f"Uploading '{src_filepath}' (size: {format_file_size(size)})"
        )

        start = time.time()
        try:
            thubmnail_id = ayon_api.create_thumbnail(
                project_name, src_filepath
            )
            self.log.debug(f"Uploaded in {time.time() - start:.2f}s.")
            return thubmnail_id

        except Exception as exc:
            last_error = exc
            self.log.warning(
                f"Thumbnail upload failed after {time.time() - start:.2f}s.",
                exc_info=True,
            )

        # Exhausted retries - raise a user-friendly validation error with help
        raise PublishXmlValidationError(
            self,
            (
                "Upload of thumbnail timed out or failed after multiple"
                " attempts. Please try publishing again."
            ),
            formatting_data={
                "upload_type": "Thumbnail",
                "file": src_filepath,
                "error": str(last_error),
            },
            help_filename="upload_file.xml",
        )

    def _integrate_thumbnails(
        self,
        filtered_instance_items,
        version_entities_by_id,
        project_name
    ):
        # Make sure each entity id has defined only one thumbnail id
        folder_ids = set()
        op_session = OperationsSession()
        for instance_item in filtered_instance_items:
            instance, thumbnail_path, version_id = instance_item
            instance_label = self._get_instance_label(instance)
            version_entity = version_entities_by_id.get(version_id)
            if not version_entity:
                self.log.warning(
                    f"Version entity for instance \"{instance_label}\""
                    f" was not found."
                )
                continue

            folder_id = instance.data["folderEntity"]["id"]
            folder_ids.add(folder_id)
            thumbnail_id = self._create_thumbnail(
                project_name, thumbnail_path
            )

            # Set thumbnail id for version
            op_session.update_entity(
                project_name,
                "version",
                version_id,
                {"thumbnailId": thumbnail_id}
            )
            version_name = version_entity["version"]
            if version_name < 0:
                version_name = "Hero"
            self.log.debug(
                f"Setting thumbnail for version \"{version_name}\""
                f" <{version_id}>"
            )

        op_session.commit()

        if folder_ids:
            endpoint = ayon_api.get_addon_endpoint(
                "core",
                __version__,
                "cleanupFolderThumbnails",
                project_name,
            )
            ayon_api.post(endpoint, folder_ids=list(folder_ids))

    def _get_instance_label(self, instance):
        return (
            instance.data.get("label")
            or instance.data.get("name")
            or "N/A"
        )
