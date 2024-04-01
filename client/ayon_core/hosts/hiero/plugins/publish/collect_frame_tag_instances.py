from pprint import pformat
import re
import ast
import json

import pyblish.api


class CollectFrameTagInstances(pyblish.api.ContextPlugin):
    """Collect frames from tags.

    Tag is expected to have metadata:
    {
        "productType": "frame"
        "productName": "main"
    }
    """

    order = pyblish.api.CollectorOrder
    label = "Collect Frames"
    hosts = ["hiero"]

    def process(self, context):
        self._context = context

        # collect all sequence tags
        product_data = self._create_frame_product_data_sequence(context)

        self.log.debug("__ product_data: {}".format(
            pformat(product_data)
        ))

        # create instances
        self._create_instances(product_data)

    def _get_tag_data(self, tag):
        data = {}

        # get tag metadata attribute
        tag_data = tag.metadata()

        # convert tag metadata to normal keys names and values to correct types
        for k, v in dict(tag_data).items():
            key = k.replace("tag.", "")

            try:
                # capture exceptions which are related to strings only
                if re.match(r"^[\d]+$", v):
                    value = int(v)
                elif re.match(r"^True$", v):
                    value = True
                elif re.match(r"^False$", v):
                    value = False
                elif re.match(r"^None$", v):
                    value = None
                elif re.match(r"^[\w\d_]+$", v):
                    value = v
                else:
                    value = ast.literal_eval(v)
            except (ValueError, SyntaxError):
                value = v

            data[key] = value

        return data

    def _create_frame_product_data_sequence(self, context):

        sequence_tags = []
        sequence = context.data["activeTimeline"]

        # get all publishable sequence frames
        publish_frames = range(int(sequence.duration() + 1))

        self.log.debug("__ publish_frames: {}".format(
            pformat(publish_frames)
        ))

        # get all sequence tags
        for tag in sequence.tags():
            tag_data = self._get_tag_data(tag)
            self.log.debug("__ tag_data: {}".format(
                pformat(tag_data)
            ))
            if not tag_data:
                continue

            product_type = tag_data.get("productType")
            if product_type is None:
                product_type = tag_data.get("family")
            if not product_type:
                continue

            if product_type != "frame":
                continue

            sequence_tags.append(tag_data)

        self.log.debug("__ sequence_tags: {}".format(
            pformat(sequence_tags)
        ))

        # first collect all available product tag frames
        product_data = {}
        context_folder_path = context.data["folderEntity"]["path"]

        for tag_data in sequence_tags:
            frame = int(tag_data["start"])

            if frame not in publish_frames:
                continue

            product_name = tag_data.get("productName")
            if product_name is None:
                product_name = tag_data["subset"]

            if product_name in product_data:
                # update existing product key
                product_data[product_name]["frames"].append(frame)
            else:
                # create new product key
                product_data[product_name] = {
                    "frames": [frame],
                    "format": tag_data["format"],
                    "folderPath": context_folder_path
                }
        return product_data

    def _create_instances(self, product_data):
        # create instance per product
        product_type = "image"
        for product_name, product_data in product_data.items():
            name = "frame" + product_name.title()
            data = {
                "name": name,
                "label": "{} {}".format(name, product_data["frames"]),
                "productType": product_type,
                "family": product_type,
                "families": [product_type, "frame"],
                "folderPath": product_data["folderPath"],
                "productName": name,
                "format": product_data["format"],
                "frames": product_data["frames"]
            }
            self._context.create_instance(**data)

            self.log.info(
                "Created instance: {}".format(
                    json.dumps(data, sort_keys=True, indent=4)
                )
            )
