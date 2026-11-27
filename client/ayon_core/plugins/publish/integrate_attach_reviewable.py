from __future__ import annotations

import copy
import os
import shutil
import weakref

import pyblish.api

from ayon_core.lib import EnumDef
from ayon_core.pipeline import OptionalPyblishPluginMixin, PublishError
from ayon_core.pipeline import get_temp_dir


class AttachReviewables(
    pyblish.api.InstancePlugin, OptionalPyblishPluginMixin
):
    """Copy extracted reviewables to their target instances.

    The plugin runs immediately after :class:`ExtractReview`.  This keeps
    review extraction shared while allowing burnins, slates and later
    instance plugins to process the copied representation in the context of
    each target instance.
    """

    families = ["render", "review"]
    order = pyblish.api.ExtractorOrder + 0.025
    label = "Attach reviewables"
    settings_category = "core"

    _metadata_keys = (
        "fps",
        "pixelAspect",
        "resolutionWidth",
        "resolutionHeight",
        "reviewToWidth",
        "reviewToHeight",
        "slateFrame",
        "slateFrames",
    )

    def process(self, instance):
        """Attach extracted review representations to configured targets."""
        if not instance.data.get("publish", True):
            return

        attach_to = self.get_attr_values_from_data(instance.data).get(
            "attach", []
        )
        if not attach_to:
            self.log.debug(
                "Reviewable is not set to attach to another instance."
            )
            return

        representations = [
            repre
            for repre in instance.data.get("representations", [])
            if self._is_review_representation(repre)
        ]
        if not representations:
            self.log.debug(
                "Reviewable has no extracted representations to attach."
            )
            return
        for repre in representations:
            if not repre.get("files"):
                raise PublishError(
                    "Cannot attach reviewable representation without files: "
                    "{}".format(repre.get("name", "<unnamed>"))
                )

        target_instances = self._get_target_instances(instance, attach_to)
        if not target_instances:
            return

        cleanup_paths = instance.context.data.setdefault(
            "cleanupFullPaths", []
        )
        cleanup_paths_before = set(cleanup_paths)
        copied_by_target = []
        try:
            for target_instance in target_instances:
                copied_by_target.append((
                    target_instance,
                    self._copy_representations(
                        instance, target_instance, representations
                    ),
                ))
        except Exception:
            for path in set(cleanup_paths) - cleanup_paths_before:
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                cleanup_paths.remove(path)
            raise

        for target_instance, copied_representations in copied_by_target:
            target_instance.data.setdefault(
                "representations", []
            ).extend(copied_representations)
            self.log.info("Attaching reviewable to %s", target_instance.name)

        instance.data["_attach_reviewable_target_ids"] = [
            target.data["instance_id"] for target in target_instances
        ]

        # The review product is only a source for the target products.  Keep
        # unrelated representations intact, but prevent this instance from
        # being integrated as a separate publish.
        for repre in representations:
            instance.data["representations"].remove(repre)
        if not instance.data.get("representations"):
            instance.data["integrate"] = False

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
            if not target_instance.data.get("publish", True):
                self.log.debug(
                    "Skipping unpublished attached instance '%s'.",
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

    @staticmethod
    def _is_review_representation(representation):
        tags = representation.get("tags") or []
        return bool(
            set(tags) & {"review", "webreview", "thumbnail"}
        )

    def _copy_representations(
        self, source_instance, target_instance, representations
    ):
        copied_representations = []
        project_name = source_instance.context.data["projectName"]

        for representation in representations:
            copied = self._safe_copy(representation)
            for key in self._metadata_keys:
                if key not in copied and key in source_instance.data:
                    copied[key] = self._safe_copy(source_instance.data[key])
            if "reviewData" not in copied:
                copied["reviewData"] = self._source_review_data(
                    source_instance
                )

            source_staging_dir = (
                representation.get("stagingDir")
                or source_instance.data.get("stagingDir")
            )
            files = representation.get("files")
            if not files:
                raise PublishError(
                    "Cannot attach reviewable representation without files: "
                    "{}".format(representation.get("name", "<unnamed>"))
                )

            source_files = files if isinstance(files, (list, tuple)) else [
                files
            ]
            source_paths = []
            for filename in source_files:
                source_path = filename
                if not os.path.isabs(filename):
                    if not source_staging_dir:
                        raise PublishError(
                            "Cannot attach reviewable representation without "
                            "a staging directory: {}".format(filename)
                        )
                    source_path = os.path.join(source_staging_dir, filename)
                if not os.path.isfile(source_path):
                    raise PublishError(
                        "Cannot attach reviewable representation because "
                        "source file is missing: {}".format(source_path)
                    )
                source_paths.append(source_path)

            target_staging_dir = get_temp_dir(
                project_name=project_name,
                prefix="ay_attach_",
                use_local_temp=True,
            )
            copied["stagingDir"] = target_staging_dir
            copied["stagingDir_persistent"] = False
            source_instance.context.data.setdefault(
                "cleanupFullPaths", []
            ).append(target_staging_dir)

            copied_files = []
            for source_path, filename in zip(source_paths, source_files):
                if os.path.isabs(filename):
                    target_filename = os.path.basename(filename)
                else:
                    target_filename = os.path.normpath(filename)
                if not target_filename:
                    target_filename = os.path.basename(source_path)
                target_root = os.path.abspath(target_staging_dir)
                target_path = os.path.abspath(
                    os.path.join(target_staging_dir, target_filename)
                )
                try:
                    is_inside_target = os.path.commonpath(
                        (target_root, target_path)
                    ) == target_root
                except ValueError:
                    is_inside_target = False
                if not is_inside_target:
                    raise PublishError(
                        "Attached reviewable filename escapes its staging "
                        "directory: {}".format(filename)
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
            if sequence_file:
                if os.path.isabs(sequence_file):
                    copied["sequence_file"] = os.path.basename(sequence_file)
                else:
                    sequence_file = os.path.normpath(sequence_file)
                    sequence_path = os.path.abspath(
                        os.path.join(target_staging_dir, sequence_file)
                    )
                    try:
                        sequence_is_inside = os.path.commonpath(
                            (target_root, sequence_path)
                        ) == target_root
                    except ValueError:
                        sequence_is_inside = False
                    if not sequence_is_inside:
                        raise PublishError(
                            "Attached reviewable sequence file escapes its "
                            "staging directory: {}".format(sequence_file)
                        )
                    copied["sequence_file"] = sequence_file

            copied_representations.append(copied)

        return copied_representations

    @classmethod
    def _source_review_data(cls, instance):
        anatomy_data = instance.data.get("anatomyData") or {}
        return cls._safe_copy({
            "frameStart": instance.data.get("frameStart"),
            "frameEnd": instance.data.get("frameEnd"),
            "handleStart": instance.data.get("handleStart"),
            "handleEnd": instance.data.get("handleEnd"),
            "productBaseType": instance.data.get(
                "productBaseType", instance.data.get("productType")
            ),
            "productName": instance.data.get("productName"),
            "families": list(instance.data.get("families") or []),
            "task": anatomy_data.get("task", {}),
            "anatomyData": anatomy_data,
            "comment": instance.data.get("comment"),
            "customData": instance.data.get("customData"),
            "customBurninData": instance.data.get("custom_burnin_data"),
            "burninDataMembers": instance.data.get("burninDataMembers"),
        })

    @staticmethod
    def _safe_copy(value):
        """Copy nested data while retaining objects that cannot be pickled."""
        if isinstance(value, weakref.WeakMethod):
            return value
        if isinstance(value, dict):
            return {
                AttachReviewables._safe_copy(key):
                AttachReviewables._safe_copy(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [AttachReviewables._safe_copy(item) for item in value]
        if isinstance(value, tuple):
            return tuple(AttachReviewables._safe_copy(item) for item in value)
        if isinstance(value, set):
            return {AttachReviewables._safe_copy(item) for item in value}
        if isinstance(value, frozenset):
            return frozenset(
                AttachReviewables._safe_copy(item) for item in value
            )
        try:
            return copy.deepcopy(value)
        except TypeError:
            return value

    @classmethod
    def get_attr_defs_for_instance(cls, create_context, instance):
        if not cls.instance_matches_plugin_families(instance):
            return []

        items = []
        for other_instance in create_context.instances:
            if other_instance == instance:
                continue
            if other_instance.product_base_type in cls.families:
                continue
            items.append(
                {
                    "label": other_instance.label,
                    "value": str(other_instance.id),
                }
            )

        return [
            EnumDef(
                "attach",
                label="Attach reviewable",
                multiselection=True,
                items=items,
                tooltip="Attach this reviewable to another instance",
            )
        ]


class FinalizeAttachReviewables(pyblish.api.ContextPlugin):
    """Attach review thumbnails created after the review extraction phase."""

    order = pyblish.api.ExtractorOrder + 0.5
    label = "Finalize attached reviewables"
    settings_category = "core"

    def process(self, context):
        attach_plugin = AttachReviewables()
        for source_instance in context:
            target_ids = source_instance.data.pop(
                "_attach_reviewable_target_ids", None
            )
            if not target_ids:
                continue

            thumbnail_representations = [
                repre
                for repre in source_instance.data.get("representations", [])
                if "thumbnail" in (repre.get("tags") or [])
            ]
            if not thumbnail_representations:
                continue

            target_instances = attach_plugin._get_target_instances(
                source_instance, target_ids
            )
            for target_instance in target_instances:
                copied_representations = attach_plugin._copy_representations(
                    source_instance,
                    target_instance,
                    thumbnail_representations,
                )
                target_instance.data.setdefault(
                    "representations", []
                ).extend(copied_representations)

            if source_instance.data.get("integrate") is False:
                for repre in thumbnail_representations:
                    source_instance.data["representations"].remove(repre)
