import json

import pyblish.api
from ayon_core.pipeline.publish import OptionalPyblishPluginMixin
from ayon_blender.api import plugin


class IntegrateAnimation(
    plugin.BlenderInstancePlugin,
    OptionalPyblishPluginMixin,
):
    """Generate a JSON file for animation."""

    label = "Integrate Animation"
    order = pyblish.api.IntegratorOrder + 0.1
    optional = True
    hosts = ["blender"]
    families = ["setdress"]

    def process(self, instance):
        self.log.debug("Integrate Animation")

        representation = instance.data.get('representations')[0]
        json_path = representation.get('publishedFiles')[0]

        with open(json_path, "r") as file:
            data = json.load(file)

        # Update the json file for the setdress to add the published
        # representations of the animations
        for json_dict in data:
            json_product_name = json_dict["productName"]
            i = None
            for elem in instance.context:
                if elem.data["productName"] == json_product_name:
                    i = elem
                    break
            if not i:
                continue
            rep = None
            pub_repr = i.data["published_representations"]
            for elem in pub_repr:
                if pub_repr[elem]["representation"]["name"] == "fbx":
                    rep = pub_repr[elem]
                    break
            if not rep:
                continue
            obj_id = rep["representation"]["id"]

            if obj_id:
                json_dict["representation_id"] = str(obj_id)

        with open(json_path, "w") as file:
            json.dump(data, fp=file, indent=2)
