import os.path
import opentimelineio

import pyblish.api

from ayon_core.pipeline import publish


class ExtractEditorialPackage(publish.Extractor):
    """Replaces movie paths in otio file with publish rootless

    Prepares movie resources for integration.
    TODO introduce conversion to .mp4
    """

    label = "Extract Editorial Package"
    order = pyblish.api.ExtractorOrder - 0.45
    hosts = ["traypublisher"]
    families = ["editorial_pckg"]

    def process(self, instance):
        editorial_pckg_data = instance.data.get("editorial_pckg")

        otio_path = editorial_pckg_data["otio_path"]
        otio_basename = os.path.basename(otio_path)
        staging_dir = self.staging_dir(instance)

        editorial_pckg_repre = {
            'name': "editorial_pckg",
            'ext': "otio",
            'files': otio_basename,
            "stagingDir": staging_dir,
        }
        otio_staging_path = os.path.join(staging_dir, otio_basename)

        instance.data["representations"].append(editorial_pckg_repre)

        publish_path = self._get_published_path(instance)
        publish_folder = os.path.dirname(publish_path)
        publish_resource_folder = os.path.join(publish_folder, "resources")

        resource_paths = editorial_pckg_data["resource_paths"]
        transfers = self._get_transfers(resource_paths,
                                        publish_resource_folder)
        if not "transfers" in instance.data:
            instance.data["transfers"] = []
        instance.data["transfers"] = transfers

        source_to_rootless = self._get_resource_path_mapping(instance,
                                                             transfers)

        otio_data = editorial_pckg_data["otio_data"]
        otio_data = self._replace_target_urls(otio_data, source_to_rootless)

        opentimelineio.adapters.write_to_file(otio_data, otio_staging_path)

        self.log.info("Added Editorial Package representation: {}".format(
            editorial_pckg_repre))

    def _get_resource_path_mapping(self, instance, transfers):
        """Returns dict of {source_mov_path: rootless_published_path}."""
        replace_paths = {}
        anatomy = instance.context.data["anatomy"]
        for source, destination in transfers:
            rootless_path = self._get_rootless(anatomy, destination)
            source_file_name = os.path.basename(source)
            replace_paths[source_file_name] = rootless_path
        return replace_paths

    def _get_transfers(self, resource_paths, publish_resource_folder):
        """Returns list of tuples (source, destination) movie paths."""
        transfers = []
        for res_path in resource_paths:
            res_basename = os.path.basename(res_path)
            pub_res_path = os.path.join(publish_resource_folder, res_basename)
            transfers.append((res_path, pub_res_path))
        return transfers

    def _replace_target_urls(self, otio_data, replace_paths):
        """Replace original movie paths with published rootles ones."""
        for track in otio_data.tracks:
            for clip in track:
                # Check if the clip has a media reference
                if clip.media_reference is not None:
                    # Access the target_url from the media reference
                    target_url = clip.media_reference.target_url
                    if not target_url:
                        continue
                    file_name = os.path.basename(target_url)
                    replace_value = replace_paths.get(file_name)
                    if replace_value:
                        clip.media_reference.target_url = replace_value

        return otio_data

    def _get_rootless(self, anatomy, path):
        """Try to find rootless {root[work]} path from `path`"""
        success, rootless_path = anatomy.find_root_template_from_path(
            path)
        if not success:
            # `rootless_path` is not set to `output_dir` if none of roots match
            self.log.warning(
               f"Could not find root path for remapping '{path}'."
            )
            rootless_path = path

        return rootless_path

    def _get_published_path(self, instance):
        """Calculates expected `publish` folder"""
        # determine published path from Anatomy.
        template_data = instance.data.get("anatomyData")
        rep = instance.data["representations"][0]
        template_data["representation"] = rep.get("name")
        template_data["ext"] = rep.get("ext")
        template_data["comment"] = None

        anatomy = instance.context.data["anatomy"]
        template_data["root"] = anatomy.roots
        template = anatomy.get_template_item("publish", "default", "path")
        template_filled = template.format_strict(template_data)
        return os.path.normpath(template_filled)
