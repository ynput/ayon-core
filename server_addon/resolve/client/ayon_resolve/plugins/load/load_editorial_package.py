from pathlib import Path

from ayon_core.pipeline import (
    load,
    get_representation_path,
)

from ayon_resolve.api import lib


class LoadEditorialPackage(load.LoaderPlugin):
    """Load editorial package to timeline.

    Loading timeline from OTIO file included media sources
    and timeline structure.
    """

    product_types = {"editorial_pkg"}

    representations = {"*"}
    extensions = {"otio"}

    label = "Load as Timeline"
    order = -10
    icon = "ei.align-left"
    color = "orange"

    def load(self, context, name, namespace, data):
        files = get_representation_path(context["representation"])

        search_folder_path = Path(files).parent / "resources"

        project = lib.get_current_project()
        media_pool = project.GetMediaPool()

        # create versioned bin for editorial package
        version_name = context["version"]["name"]
        bin_name = f"{name}_{version_name}"
        lib.create_bin(bin_name)

        import_options = {
            "timelineName": "Editorial Package Timeline",
            "importSourceClips": True,
            "sourceClipsPath": search_folder_path.as_posix(),
        }

        timeline = media_pool.ImportTimelineFromFile(files, import_options)
        print("Timeline imported: ", timeline)

    def update(self, container, context):
        # TODO: implement update method in future
        pass
