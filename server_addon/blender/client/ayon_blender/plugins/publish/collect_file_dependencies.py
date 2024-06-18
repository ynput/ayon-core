from pathlib import Path

import pyblish.api

import bpy


class CollectFileDependencies(pyblish.api.ContextPlugin):
    """Gather all files referenced in this scene."""

    label = "Collect File Dependencies"
    order = pyblish.api.CollectorOrder - 0.49
    hosts = ["blender"]
    families = ["render"]

    @classmethod
    def apply_settings(cls, project_settings):
        # Disable plug-in if not used for deadline submission anyway
        settings = project_settings["deadline"]["publish"]["BlenderSubmitDeadline"]  # noqa
        cls.enabled = settings.get("asset_dependencies", True)

    def process(self, context):
        dependencies = set()

        # Add alembic files as dependencies
        for cache in bpy.data.cache_files:
            dependencies.add(
                Path(bpy.path.abspath(cache.filepath)).resolve().as_posix())

        # Add image files as dependencies
        for image in bpy.data.images:
            if image.filepath:
                dependencies.add(Path(
                    bpy.path.abspath(image.filepath)).resolve().as_posix())

        context.data["fileDependencies"] = list(dependencies)
