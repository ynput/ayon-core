import inspect

import os
from collections import defaultdict

import pyblish.api
from ayon_core.pipeline.publish import (
    ValidateContentsOrder,
    PublishValidationError
)


class ValidateResources(pyblish.api.InstancePlugin):
    """Validates mapped resources.

    These are external files to the current application, for example
    these could be textures, image planes, cache files or other linked
    media.

    A single resource entry MUST contain `source` and `files`:
        {
            "source": "/path/to/file.<UDIM>.exr",
            "files": ['/path/to/file.1001.exr', '/path/to/file.1002.exr']
        }

    It may contain additional metadata like `attribute` or `node` so other
    publishing plug-ins can detect where the resource was used. The
    `color_space` data is also frequently used (e.g. in Maya and Houdini)

    This validates:
        - The resources are existing files.
        - The resources have correctly collected the data.
        - The resources must be unique to the source filepath so that multiple
          source filepaths do not write to the same publish filepath.

    """

    order = ValidateContentsOrder
    label = "Resources"

    def process(self, instance):

        resources = instance.data.get("resources", [])
        if not resources:
            self.log.debug("No resources to validate..")
            return

        # Validate the `resources` data structure is valid
        invalid_data = False
        for resource in resources:
            # Required data
            if "source" not in resource:
                invalid_data = True
                self.log.error("Missing 'source' in resource: %s", resource)
            if "files" not in resource or not resource["files"]:
                invalid_data = True
                self.log.error("Missing 'files' in resource: %s", resource)
            if not all(os.path.exists(f) for f in resource.get("files", [])):
                invalid_data = True
                self.log.error(
                    "Resource contains files that do not exist "
                    "on disk: %s", resource
                )

        # Ensure unique resource names
        basenames = defaultdict(set)
        for resource in resources:
            files = resource.get("files", [])
            for filename in files:

                # Use normalized paths in comparison and ignore case
                # sensitivity
                filename = os.path.normpath(filename).lower()

                basename = os.path.splitext(os.path.basename(filename))[0]
                basenames[basename].add(filename)

        invalid_resources = list()
        for basename, sources in basenames.items():
            if len(sources) > 1:
                invalid_resources.extend(sources)
                self.log.error(
                    "Non-unique resource filename: {0}\n- {1}".format(
                        basename,
                        "\n- ".join(sources)
                    )
                )

        if invalid_data or invalid_resources:
            raise PublishValidationError(
                "Invalid resources in instance.",
                description=self.get_description()
            )

    def get_description(self):
        return inspect.cleandoc(
            """### Invalid resources

            Used resources, like textures, must exist on disk and must have
            unique filenames.

            #### Filenames must be unique

            In most cases this will invalidate  due to using the same filenames
            from different folders, and as such the file to be transferred is
            unique but has the same filename. Either rename the source files or
            make sure to use the same source file if they are intended to
            be the same file.

            """
        )
