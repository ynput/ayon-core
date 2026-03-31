import os
import time

import ayon_api
import pyblish.api

from ayon_core.lib import get_media_mime_type, format_file_size
from ayon_core.pipeline.publish import (
    PublishXmlValidationError,
    get_publish_repre_path,
)


class IntegrateAYONReview(pyblish.api.InstancePlugin):
    label = "Integrate AYON Review"
    # Must happen after IntegrateAsset
    order = pyblish.api.IntegratorOrder + 0.15

    def process(self, instance):
        project_name = instance.context.data["projectName"]
        src_version_entity = instance.data.get("versionEntity")
        src_hero_version_entity = instance.data.get("heroVersionEntity")
        for version_entity in (
            src_version_entity,
            src_hero_version_entity,
        ):
            if not version_entity:
                continue

            version_id = version_entity["id"]
            self._upload_reviewable(project_name, version_id, instance)

    def _upload_reviewable(self, project_name, version_id, instance):
        ayon_con = ayon_api.get_server_api_connection()
        major, minor, _, _, _ = ayon_con.get_server_version_tuple()
        if (major, minor) < (1, 3):
            self.log.info(
                "Skipping reviewable upload, supported from server 1.3.x."
                f" Current server version {ayon_con.get_server_version()}"
            )
            return

        uploaded_labels = set()
        for repre in instance.data["representations"]:
            repre_tags = repre.get("tags") or []
            # Ignore representations that are not reviewable
            if "webreview" not in repre_tags:
                continue

            # exclude representations going to be published on farm
            if "publish_on_farm" in repre_tags:
                continue

            # Skip thumbnails
            if repre.get("thumbnail") or "thumbnail" in repre_tags:
                continue

            repre_path = get_publish_repre_path(
                instance, repre, False
            )
            if not repre_path or not os.path.exists(repre_path):
                # TODO log skipper path
                continue

            content_type = get_media_mime_type(repre_path)
            if not content_type:
                self.log.warning(
                    f"Could not determine Content-Type for {repre_path}"
                )
                continue

            label = self._get_review_label(repre, uploaded_labels)

            size = os.path.getsize(repre_path)
            start = time.time()
            self.log.info(
                f"Uploading '{repre_path}' (size: {format_file_size(size)})"
            )
            try:
                ayon_api.upload_reviewable(
                    project_name,
                    version_id,
                    repre_path,
                    content_type=content_type,
                    label=label,
                )
            except Exception as exc:
                self.log.warning(
                    f"Review upload failed after {time.time() - start}s.",
                    exc_info=True,
                )
                raise PublishXmlValidationError(
                    self,
                    (
                        "Upload of reviewable timed out or failed after"
                        " multiple attempts. Please try publishing again."
                    ),
                    formatting_data={
                        "upload_type": "Review",
                        "file": repre_path,
                        "error": str(exc),
                    },
                    help_filename="upload_file.xml",
                )

    def _get_review_label(self, repre, uploaded_labels):
        # Use output name as label if available
        label = repre.get("outputName")
        if not label:
            return None
        orig_label = label
        idx = 0
        while label in uploaded_labels:
            idx += 1
            label = f"{orig_label}_{idx}"
        return label
