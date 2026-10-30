from __future__ import annotations

import copy
import os
import shutil

import pyblish.api

from ayon_core.pipeline import get_temp_dir
from ayon_core.pipeline.publish.lib import add_repre_files_for_cleanup

ATTACH_TARGET_ID_KEY = "_attach_reviewable_target_id"


def get_target_version(instance):
    """Return the version that will be used by a target instance."""
    version_entity = instance.data.get("versionEntity") or {}
    version = version_entity.get("version")
    if version is not None:
        return version

    anatomy_data = instance.data.get("anatomyData") or {}
    version = anatomy_data.get("version")
    if version is not None:
        return version

    version = instance.data.get("version")
    if version is not None:
        return version

    latest_version = instance.data.get("latestVersion")
    if latest_version is not None:
        return int(latest_version) + 1


class PrepareAttachReviewables(pyblish.api.ContextPlugin):
    """Prepare one review instance for every attached target instance."""

    order = pyblish.api.ExtractorOrder + 0.025
    label = "Prepare attached reviewables"
    settings_category = "core"

    @classmethod
    def apply_settings(cls, project_settings):
        """Use the same enabled setting as ``AttachReviewables``."""
        cls.enabled = project_settings.get(
            "core", {}
        ).get(
            "publish", {}
        ).get(
            "AttachReviewables", {}
        ).get("enabled", True)

    def process(self, context):
        """Create target-specific instances before review burnins run."""
        for instance in tuple(context):
            if not instance.data.get("publish", True):
                continue
            if not instance.data.get("active", True):
                continue
            if not self._is_reviewable(instance):
                continue

            attach_to = self._get_attach_targets(instance)
            if not attach_to:
                continue

            target_instances = self._get_target_instances(
                instance, attach_to
            )
            if not target_instances:
                continue

            representations = instance.data.get("representations") or []
            for target_instance in target_instances:
                self._create_target_instance(
                    context,
                    instance,
                    target_instance,
                    representations,
                )

            # The source review is replaced by the target-specific instances.
            # This prevents the source from producing one shared burnin.
            instance.data["publish"] = False

    def _get_attach_targets(self, instance):
        publish_attributes = instance.data.get("publish_attributes", {})
        attach_reviewables = publish_attributes.get("AttachReviewables", {})
        return attach_reviewables.get("attach") or []

    def _is_reviewable(self, instance):
        families = set(instance.data.get("families") or [])
        families.add(instance.data.get("family"))
        families.add(instance.data.get("productBaseType"))
        families.add(instance.data.get("productType"))
        return bool(families & {"render", "review"})

    def _get_target_instances(self, instance, attach_to):
        target_instances = []
        for target_id in attach_to:
            target_instance = next(
                (
                    candidate
                    for candidate in instance.context
                    if candidate.data.get("instance_id") == target_id
                ),
                None,
            )
            if target_instance is None:
                self.log.warning(
                    "Attached instance id '%s' was not found in context.",
                    target_id,
                )
                continue
            if not target_instance.data.get("active", True):
                self.log.debug(
                    "Skipping inactive attached instance '%s'.",
                    target_instance.name,
                )
                continue
            if target_instance.data.get("farm"):
                self.log.warning(
                    "Attaching to farm instances is not supported yet."
                )
                continue
            target_instances.append(target_instance)
        return target_instances

    def _create_target_instance(
        self,
        context,
        source_instance,
        target_instance,
        representations,
    ):
        target_name = target_instance.data.get(
            "name", target_instance.name
        )
        instance = context.create_instance(
            "{} -> {}".format(source_instance.name, target_name)
        )
        instance.data.update(copy.deepcopy(source_instance.data))
        instance.data["instance_id"] = str(instance.id)
        instance.data["representations"] = self._copy_representations(
            instance, representations
        )
        instance.data["integrate"] = False
        instance.data[ATTACH_TARGET_ID_KEY] = target_instance.data[
            "instance_id"
        ]

        # The target version is used by anatomy templates and burnins while
        # the source review settings and representations remain unchanged.
        target_version = get_target_version(target_instance)
        if target_version is not None:
            instance.data["version"] = copy.deepcopy(target_version)

            anatomy_data = instance.data.get("anatomyData")
            if anatomy_data is not None:
                anatomy_data["version"] = copy.deepcopy(target_version)

        # Do not allow the generated instance to be treated as another
        # user-configured attachment.
        instance.data["publish_attributes"] = {}

    def _copy_representations(self, instance, representations):
        """Copy source files into target-specific staging directories."""
        copied_representations = []
        staging_dirs = {}
        project_name = instance.context.data["projectName"]

        for representation in representations:
            copied = copy.deepcopy(representation)
            source_staging_dir = representation.get("stagingDir")
            files = representation.get("files")
            if not source_staging_dir or not files:
                copied_representations.append(copied)
                continue

            source_files = files if isinstance(files, (list, tuple)) else [
                files
            ]
            if not all(
                os.path.isfile(os.path.join(source_staging_dir, filename))
                for filename in source_files
            ):
                copied_representations.append(copied)
                continue

            if source_staging_dir not in staging_dirs:
                staging_dirs[source_staging_dir] = get_temp_dir(
                    project_name=project_name,
                    prefix="ay_attach_",
                    use_local_temp=True,
                )
            target_staging_dir = staging_dirs[source_staging_dir]
            copied["stagingDir"] = target_staging_dir
            copied["stagingDir_persistent"] = False

            copied_files = []
            for filename in source_files:
                target_filename = filename
                if os.path.isabs(filename):
                    target_filename = os.path.basename(filename)

                source_path = os.path.join(source_staging_dir, filename)
                target_path = os.path.join(
                    target_staging_dir, target_filename
                )
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                shutil.copy2(source_path, target_path)
                copied_files.append(target_filename)

            if isinstance(files, tuple):
                copied["files"] = tuple(copied_files)
            elif isinstance(files, list):
                copied["files"] = copied_files
            else:
                copied["files"] = copied_files[0]

            sequence_file = copied.get("sequence_file")
            if sequence_file and os.path.isabs(sequence_file):
                copied["sequence_file"] = os.path.basename(sequence_file)

            add_repre_files_for_cleanup(instance, copied)
            copied_representations.append(copied)

        source_staging_dir = instance.data.get("stagingDir")
        if source_staging_dir in staging_dirs:
            instance.data["stagingDir"] = staging_dirs[source_staging_dir]

        return copied_representations
