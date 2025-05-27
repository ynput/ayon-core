# -*- coding: utf-8 -*-
"""Cleanup leftover files from publish."""
import os
import re
import shutil
import tempfile

import pyblish.api

from ayon_core.lib import is_in_tests
from ayon_core.pipeline import PublishError


class CleanUp(pyblish.api.InstancePlugin):
    """Cleans up the staging directory after a successful publish.

    This will also clean published renders and delete their parent directories.

    """

    order = pyblish.api.IntegratorOrder + 10
    label = "Clean Up"
    hosts = [
        "aftereffects",
        "blender",
        "celaction",
        "flame",
        "fusion",
        "harmony",
        "hiero",
        "houdini",
        "maya",
        "nuke",
        "photoshop",
        "resolve",
        "tvpaint",
        "unreal",
        "webpublisher",
        "shell"
    ]
    exclude_families = ["clip"]
    optional = True
    active = True

    # Presets
    patterns = None  # list of regex patterns
    remove_temp_renders = True

    def process(self, instance):
        """Plugin entry point."""
        if is_in_tests():
            # let automatic test process clean up temporary data
            return

        # If instance has errors, do not clean up
        for result in instance.context.data["results"]:
            if result["error"] is not None and result["instance"] is instance:
                raise PublishError(
                    "Result of '{}' instance were not success".format(
                        instance.data["name"]
                    )
                )

        _skip_cleanup_filepaths = instance.context.data.get(
            "skipCleanupFilepaths"
        ) or []
        skip_cleanup_filepaths = set()
        for path in _skip_cleanup_filepaths:
            skip_cleanup_filepaths.add(os.path.normpath(path))

        if self.remove_temp_renders:
            self.log.debug("Cleaning renders new...")
            self.clean_renders(instance, skip_cleanup_filepaths)

        # TODO: Figure out whether this could be refactored to just a
        #  product_type in self.exclude_families check.
        product_type = instance.data["productType"]
        if any(
            exclude_family in product_type
            for exclude_family in self.exclude_families
        ):
            self.log.debug(
                "Skipping cleanup for instance because product "
                f"type is excluded from cleanup: {product_type}")
            return

        temp_root = tempfile.gettempdir()
        staging_dir = instance.data.get("stagingDir", None)

        if not staging_dir:
            self.log.debug("Skipping cleanup. Staging dir not set "
                           "on instance: {}.".format(instance))
            return

        if not os.path.normpath(staging_dir).startswith(temp_root):
            self.log.debug("Skipping cleanup. Staging directory is not in the "
                           "temp folder: %s" % staging_dir)
            return

        if not os.path.exists(staging_dir):
            self.log.debug("No staging directory found at: %s" % staging_dir)
            return

        if instance.data.get("stagingDir_persistent"):
            self.log.debug(
                "Staging dir {} should be persistent".format(staging_dir)
            )
            return

        self.log.debug("Removing staging directory {}".format(staging_dir))
        shutil.rmtree(staging_dir)

    def clean_renders(self, instance, skip_cleanup_filepaths):
        transfers = instance.data.get("transfers", list())

        instance_families = instance.data.get("families", list())
        instance_product_type = instance.data.get("productType")
        dirnames = []
        transfers_dirs = []

        for src, dest in transfers:
            # fix path inconsistency
            src = os.path.normpath(src)
            dest = os.path.normpath(dest)

            # add src dir into clearing dir paths (regex patterns)
            transfers_dirs.append(os.path.dirname(src))

            # add dest dir into clearing dir paths (regex patterns)
            transfers_dirs.append(os.path.dirname(dest))

            if src in skip_cleanup_filepaths:
                self.log.debug((
                    "Source file is marked to be skipped in cleanup. {}"
                ).format(src))
                continue

            if os.path.normpath(src) == os.path.normpath(dest):
                continue

            if (
                instance_product_type == "render"
                or "render" in instance_families
            ):
                self.log.info("Removing src: `{}`...".format(src))
                try:
                    os.remove(src)
                except PermissionError:
                    self.log.warning(
                        "Insufficient permission to delete {}".format(src)
                    )
                    continue

                # add dir for cleanup
                dirnames.append(os.path.dirname(src))

        # clean by regex patterns
        # make unique set
        transfers_dirs = set(transfers_dirs)

        self.log.debug("__ transfers_dirs: `{}`".format(transfers_dirs))
        self.log.debug("__ self.patterns: `{}`".format(self.patterns))
        if self.patterns:
            files = list()
            # get list of all available content of dirs
            for _dir in transfers_dirs:
                if not os.path.exists(_dir):
                    continue
                files.extend([
                    os.path.join(_dir, f)
                    for f in os.listdir(_dir)])

            self.log.debug("__ files: `{}`".format(files))

            # remove all files which match regex pattern
            for f in files:
                if os.path.normpath(f) in skip_cleanup_filepaths:
                    continue

                for p in self.patterns:
                    pattern = re.compile(p)
                    if not pattern.findall(f):
                        continue
                    if not os.path.exists(f):
                        continue

                    self.log.info("Removing file by regex: `{}`".format(f))
                    os.remove(f)

                    # add dir for cleanup
                    dirnames.append(os.path.dirname(f))

        # make unique set
        cleanup_dirs = set(dirnames)

        # clean dirs which are empty
        for dir in cleanup_dirs:
            try:
                os.rmdir(dir)
            except OSError:
                # directory is not empty, skipping
                continue
