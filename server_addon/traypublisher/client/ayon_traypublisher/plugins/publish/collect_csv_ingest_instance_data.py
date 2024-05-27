from pprint import pformat
import pyblish.api
from ayon_core.pipeline import publish


class CollectCSVIngestInstancesData(
    pyblish.api.InstancePlugin,
    publish.AYONPyblishPluginMixin,
    publish.ColormanagedPyblishPluginMixin
):
    """Collect CSV Ingest data from instance.
    """

    label = "Collect CSV Ingest instances data"
    order = pyblish.api.CollectorOrder + 0.1
    hosts = ["traypublisher"]
    families = ["csv_ingest"]

    def process(self, instance):

        # expecting [(colorspace, repre_data), ...]
        prepared_repres_data_items = instance.data[
            "prepared_data_for_repres"]

        for prep_repre_data in prepared_repres_data_items:
            type = prep_repre_data["type"]
            colorspace = prep_repre_data["colorspace"]
            repre_data = prep_repre_data["representation"]

            # thumbnails should be skipped
            if type == "media":
                # colorspace name is passed from CSV column
                self.set_representation_colorspace(
                    repre_data, instance.context, colorspace
                )
            elif type == "media" and colorspace is None:
                # TODO: implement colorspace file rules file parsing
                self.log.warning(
                    "Colorspace is not defined in csv for following"
                    f" representation: {pformat(repre_data)}"
                )
                pass
            elif type == "thumbnail":
                # thumbnails should be skipped
                pass

            instance.data["representations"].append(repre_data)
