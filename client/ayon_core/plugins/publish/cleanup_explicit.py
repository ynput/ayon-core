# -*- coding: utf-8 -*-
"""Cleanup files when publishing is done."""
import os
import shutil
import pyblish.api


class ExplicitCleanUp(pyblish.api.ContextPlugin):
    """Cleans up the files and folder defined to be deleted.

    plugin is looking for 2 keys into context data:
    - `cleanupFullPaths` - full paths that should be removed not matter if
        is path to file or to directory
    - `cleanupEmptyDirs` - full paths to directories that should be removed
        only if do not contain any file in it but will be removed if contain
        sub-folders
    """

    order = pyblish.api.IntegratorOrder + 10
    label = "Explicit Clean Up"
    optional = True
    active = True

    def process(self, context):
        cleanup_full_paths = context.data.get("cleanupFullPaths")
        cleanup_empty_dirs = context.data.get("cleanupEmptyDirs")

        self._remove_full_paths(cleanup_full_paths)
        self._remove_empty_dirs(cleanup_empty_dirs)

    def _remove_full_paths(self, full_paths):
        """Remove files and folders from disk.

        Folders are removed with whole content.
        """
        if not full_paths:
            self.log.debug("No full paths to cleanup were collected.")
            return

        # Separate paths into files and directories
        filepaths = set()
        dirpaths = set()
        for path in full_paths:
            # Skip empty items
            if not path:
                continue
            # Check if path exists
            if not os.path.exists(path):
                continue

            # Normalize path
            normalized = os.path.normpath(path)
            if os.path.isfile(normalized):
                filepaths.add(normalized)
            else:
                dirpaths.add(normalized)

        # Store failed paths with exception
        failed = []
        # Store removed filepaths for logging
        succeeded_files = set()
        # Remove file by file
        for filepath in filepaths:
            try:
                os.remove(filepath)
                succeeded_files.add(filepath)
            except Exception as exc:
                failed.append((filepath, exc))

        if succeeded_files:
            self.log.info(
                "Removed files:\n{}".format("\n".join(sorted(succeeded_files)))
            )

        # Delete folders with its content
        succeeded_dirs = set()
        for dirpath in dirpaths:
            # Check if directory still exists
            #   - it is possible that directory was already deleted with
            #       different dirpath to delete
            if os.path.exists(dirpath):
                try:
                    shutil.rmtree(dirpath)
                    succeeded_dirs.add(dirpath)
                except Exception:
                    failed.append(dirpath)

        if succeeded_dirs:
            self.log.info(
                "Removed directories:\n{}".format(
                    "\n".join(sorted(succeeded_dirs))
                )
            )

        # Prepare lines for report of failed removals
        lines = [f"{filepath}: {exc}" for filepath, exc in failed]

        if lines:
            self.log.warning(
                "Failed to remove filepaths:\n{}".format(
                    "\n".join(sorted(lines))
                )
            )

    def _remove_empty_dirs(self, empty_dirpaths):
        """Remove directories if do not contain any files."""
        if not empty_dirpaths:
            self.log.debug("No empty dirs to cleanup were collected.")
            return

        # First filtering of directories and making sure those are
        #   existing directories
        filtered_dirpaths = set()
        for path in empty_dirpaths:
            if path and os.path.isdir(path):
                filtered_dirpaths.add(os.path.normpath(path))

        to_delete_dirpaths = set()
        to_skip_dirpaths = set()
        # Check if contain any files (or it's subfolders contain files)
        for dirpath in filtered_dirpaths:
            valid = True
            for _, _, filenames in os.walk(dirpath):
                if filenames:
                    valid = False
                    break

            if valid:
                to_delete_dirpaths.add(dirpath)
            else:
                to_skip_dirpaths.add(dirpath)

        if to_skip_dirpaths:
            self.log.debug(
                "Skipped directories because they contain files:\n{}".format(
                    "\n".join(sorted(to_skip_dirpaths))
                )
            )

        # Remove empty directies
        for dirpath in to_delete_dirpaths:
            if os.path.exists(dirpath):
                shutil.rmtree(dirpath)

        if to_delete_dirpaths:
            self.log.debug(
                "Deleted empty directories:\n{}".format(
                    "\n".join(sorted(to_delete_dirpaths))
                )
            )
