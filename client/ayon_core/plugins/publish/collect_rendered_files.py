"""Loads publishing context from json and continues in publish process.

Requires:
    anatomy -> context["anatomy"] *(pyblish.api.CollectorOrder - 0.4)

Provides:
    context, instances -> All data from previous publishing process.
"""

import os
import json

import pyblish.api

from ayon_core.pipeline import KnownPublishError
from ayon_core.pipeline.publish.lib import add_repre_files_for_cleanup


class CollectRenderedFiles(pyblish.api.ContextPlugin):
    """
    This collector will try to find json files in provided
    `AYON_PUBLISH_DATA`. Those files _MUST_ share same context.

    Note:
        We should split this collector and move the part which handle reading
            of file and it's context from session data before collect anatomy
            and instance creation dependent on anatomy can be done here.
    """

    order = pyblish.api.CollectorOrder - 0.2
    # Keep "filesequence" for backwards compatibility of older jobs
    targets = ["filesequence", "farm"]
    label = "Collect rendered frames"

    _context = None

    def _load_json(self, path):
        path = path.strip('\"')

        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"Path to json file doesn't exist. \"{path}\"")

        data = None
        with open(path, "r") as json_file:
            try:
                data = json.load(json_file)
            except Exception as exc:
                self.log.error(
                    "Error loading json: %s - Exception: %s", path, exc)
        return data

    def _fill_staging_dir(self, data_object, anatomy):
        staging_dir = data_object.get("stagingDir")
        if staging_dir:
            data_object["stagingDir"] = anatomy.fill_root(staging_dir)
            self.log.debug("Filling stagingDir with root to: %s",
                           data_object["stagingDir"])

    def _process_path(self, data, anatomy):
        """Process data of a single JSON publish metadata file.

        Args:
            data: The loaded metadata from the JSON file
            anatomy: Anatomy for the current context

        Returns:
            bool: Whether any instance of this particular metadata file
                has a persistent staging dir.

        """
        # validate basic necessary data
        data_err = "invalid json file - missing data"
        required = ["user", "comment",
                    "job", "instances", "version"]

        if any(elem not in data for elem in required):
            raise ValueError(data_err)

        if "folderPath" not in data and "asset" not in data:
            raise ValueError(data_err)

        if "folderPath" not in data:
            data["folderPath"] = data.pop("asset")

        # ftrack credentials are passed as environment variables by Deadline
        # to publish job, but Muster doesn't pass them.
        if data.get("ftrack") and not os.environ.get("FTRACK_API_USER"):
            ftrack = data.get("ftrack")
            os.environ["FTRACK_API_USER"] = ftrack["FTRACK_API_USER"]
            os.environ["FTRACK_API_KEY"] = ftrack["FTRACK_API_KEY"]
            os.environ["FTRACK_SERVER"] = ftrack["FTRACK_SERVER"]

        # now we can just add instances from json file and we are done
        any_staging_dir_persistent = False
        for instance_data in data.get("instances"):

            self.log.debug("  - processing instance for {}".format(
                instance_data.get("productName")))
            instance = self._context.create_instance(
                instance_data.get("productName")
            )

            self._fill_staging_dir(instance_data, anatomy)
            instance.data.update(instance_data)

            # stash render job id for later validation
            instance.data["render_job_id"] = data.get("job").get("_id")
            staging_dir_persistent = instance.data.get(
                "stagingDir_persistent", False
            )
            if staging_dir_persistent:
                any_staging_dir_persistent = True

            representations = []
            for repre_data in instance_data.get("representations") or []:
                self._fill_staging_dir(repre_data, anatomy)
                representations.append(repre_data)

                if not staging_dir_persistent:
                    add_repre_files_for_cleanup(instance, repre_data)

            instance.data["representations"] = representations

            # add audio if in metadata data
            if data.get("audio"):
                instance.data.update({
                    "audio": [{
                        "filename": data.get("audio"),
                        "offset": 0
                    }]
                })
                self.log.debug(
                    f"Adding audio to instance: {instance.data['audio']}")

        return any_staging_dir_persistent

    def process(self, context):
        self._context = context

        publish_data_paths = os.environ.get("AYON_PUBLISH_DATA")
        if not publish_data_paths:
            raise KnownPublishError("Missing `AYON_PUBLISH_DATA`")

        # QUESTION
        #   Do we support (or want support) multiple files in the variable?
        #   - what if they have different context?
        paths = publish_data_paths.split(os.pathsep)

        # Using already collected Anatomy
        anatomy = context.data["anatomy"]
        self.log.debug("Getting root setting for project \"{}\"".format(
            anatomy.project_name
        ))

        self.log.debug("Anatomy roots: {}".format(anatomy.roots))
        try:
            session_is_set = False
            for path in paths:
                path = anatomy.fill_root(path)
                data = self._load_json(path)
                assert data, "failed to load json file"
                session_data = data.get("session")
                if not session_is_set and session_data:
                    session_is_set = True
                    self.log.debug("Setting session using data from file")
                    os.environ.update(session_data)

                staging_dir_persistent = self._process_path(data, anatomy)
                if not staging_dir_persistent:
                    context.data["cleanupFullPaths"].append(path)
                    context.data["cleanupEmptyDirs"].append(
                        os.path.dirname(path)
                    )

            # Remap workdir if it's set
            workdir = os.getenv("AYON_WORKDIR")
            remapped_workdir = None
            if workdir:
                remapped_workdir = anatomy.roots_obj.path_remapper(
                    os.getenv("AYON_WORKDIR")
                )
            if remapped_workdir:
                os.environ["AYON_WORKDIR"] = remapped_workdir
        except Exception as e:
            self.log.error(e, exc_info=True)
            raise Exception("Error") from e
