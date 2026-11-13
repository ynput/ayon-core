from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional

import ayon_api
import pyblish.api

from ayon_core.lib import get_media_mime_type, format_file_size
from ayon_core.pipeline.publish import (
    PublishXmlValidationError,
    get_publish_repre_path,
)


def _get_max_upload_workers() -> int:
    """Number of reviewables uploaded concurrently.

    Can be overridden with 'AYON_PUBLISH_UPLOAD_WORKERS' env variable.
    """
    try:
        value = int(os.getenv("AYON_PUBLISH_UPLOAD_WORKERS", 4))
    except ValueError:
        value = 4
    return max(1, value)


@dataclass
class ReviewableUpload:
    version_id: str
    path: str
    content_type: str
    label: Optional[str]


class IntegrateAYONReview(pyblish.api.InstancePlugin):
    label = "Integrate AYON Review"
    # Must happen after IntegrateAsset
    order = pyblish.api.IntegratorOrder + 0.15

    def process(self, instance):
        project_name = instance.context.data["projectName"]
        src_version_entity = instance.data.get("versionEntity")
        src_hero_version_entity = instance.data.get("heroVersionEntity")
        uploads: list[ReviewableUpload] = []
        for version_entity in (
            src_version_entity,
            src_hero_version_entity,
        ):
            if not version_entity:
                continue

            version_id = version_entity["id"]
            uploads.extend(self._collect_uploads(version_id, instance))

        if not uploads:
            return

        # Upload reviewables concurrently to reduce the impact of
        # per-request latency to the server
        max_workers = min(_get_max_upload_workers(), len(uploads))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(self._upload_reviewable, project_name, upload)
                for upload in uploads
            ]
            # Wait for all uploads, re-raise the first error
            for future in futures:
                future.result()

        instance.data["hasWebreview"] = True

    def _collect_uploads(
        self, version_id: str, instance: pyblish.api.Instance
    ) -> list[ReviewableUpload]:
        uploads = []
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
            if label:
                uploaded_labels.add(label)
            uploads.append(
                ReviewableUpload(
                    version_id=version_id,
                    path=repre_path,
                    content_type=content_type,
                    label=label,
                )
            )
        return uploads

    def _upload_reviewable(
        self, project_name: str, upload: ReviewableUpload
    ) -> None:
        repre_path = upload.path
        size = os.path.getsize(repre_path)
        start = time.time()
        self.log.info(
            f"Uploading '{repre_path}' (size: {format_file_size(size)})"
        )
        try:
            ayon_api.upload_reviewable(
                project_name,
                upload.version_id,
                repre_path,
                content_type=upload.content_type,
                label=upload.label,
                # Pass headers to fix bug in ayon-api (fixed in 1.2.15)
                headers={},
            )
            self.log.debug(
                f"Uploaded '{repre_path}' in {time.time() - start:.2f}s."
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
