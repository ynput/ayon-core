from pprint import pformat

import pyblish

from ayon_core.pipeline import AYON_INSTANCE_ID, AVALON_INSTANCE_ID
from ayon_resolve.api.lib import (
    get_current_timeline_items,
    get_timeline_item_pype_tag,
    publish_clip_color,
    get_publish_attribute,
    get_otio_clip_instance_data,
)


class PrecollectInstances(pyblish.api.ContextPlugin):
    """Collect all Track items selection."""

    order = pyblish.api.CollectorOrder - 0.49
    label = "Precollect Instances"
    hosts = ["resolve"]

    def process(self, context):
        otio_timeline = context.data["otioTimeline"]
        selected_timeline_items = get_current_timeline_items(
            filter=True, selecting_color=publish_clip_color)

        self.log.info(
            "Processing enabled track items: {}".format(
                len(selected_timeline_items)))

        for timeline_item_data in selected_timeline_items:

            data = {}
            timeline_item = timeline_item_data["clip"]["item"]

            # get pype tag data
            tag_data = get_timeline_item_pype_tag(timeline_item)
            self.log.debug(f"__ tag_data: {pformat(tag_data)}")

            if not tag_data:
                continue

            if tag_data.get("id") not in {
                AYON_INSTANCE_ID, AVALON_INSTANCE_ID
            }:
                continue

            media_pool_item = timeline_item.GetMediaPoolItem()
            source_duration = int(media_pool_item.GetClipProperty("Frames"))

            # solve handles length
            handle_start = min(
                tag_data["handleStart"], int(timeline_item.GetLeftOffset()))
            handle_end = min(
                tag_data["handleEnd"], int(
                    source_duration - timeline_item.GetRightOffset()))

            self.log.debug("Handles: <{}, {}>".format(handle_start, handle_end))

            # add tag data to instance data
            data.update({
                k: v for k, v in tag_data.items()
                if k not in ("id", "applieswhole", "label")
            })

            folder_path = tag_data["folder_path"]
            # Backward compatibility fix of 'entity_type' > 'folder_type'
            if "parents" in data:
                for parent in data["parents"]:
                    if "entity_type" in parent:
                        parent["folder_type"] = parent.pop("entity_type")

            # TODO: remove backward compatibility
            product_name = tag_data.get("productName")
            if product_name is None:
                # backward compatibility: subset -> productName
                product_name = tag_data.get("subset")

            # backward compatibility: product_name should not be missing
            if not product_name:
                self.log.error(
                    "Product name is not defined for: {}".format(folder_path))

            # TODO: remove backward compatibility
            product_type = tag_data.get("productType")
            if product_type is None:
                # backward compatibility: family -> productType
                product_type = tag_data.get("family")

            # backward compatibility: product_type should not be missing
            if not product_type:
                self.log.error(
                    "Product type is not defined for: {}".format(folder_path))

            data.update({
                "name": "{}_{}".format(folder_path, product_name),
                "label": "{} {}".format(folder_path, product_name),
                "folderPath": folder_path,
                "item": timeline_item,
                "publish": get_publish_attribute(timeline_item),
                "fps": context.data["fps"],
                "handleStart": handle_start,
                "handleEnd": handle_end,
                "newHierarchyIntegration": True,
                # Backwards compatible (Deprecated since 24/06/06)
                "newAssetPublishing": True,
                "families": ["clip"],
                "productType": product_type,
                "productName": product_name,
                "family": product_type
            })

            # otio clip data
            otio_data = get_otio_clip_instance_data(
                otio_timeline, timeline_item_data) or {}
            data.update(otio_data)

            # add resolution
            self.get_resolution_to_data(data, context)

            # create instance
            instance = context.create_instance(**data)

            # create shot instance for shot attributes create/update
            self.create_shot_instance(context, timeline_item, **data)

            self.log.info("Creating instance: {}".format(instance))
            self.log.debug(
                "_ instance.data: {}".format(pformat(instance.data)))

    def get_resolution_to_data(self, data, context):
        assert data.get("otioClip"), "Missing `otioClip` data"

        # solve source resolution option
        if data.get("sourceResolution", None):
            otio_clip_metadata = data[
                "otioClip"].media_reference.metadata
            data.update({
                "resolutionWidth": otio_clip_metadata["width"],
                "resolutionHeight": otio_clip_metadata["height"],
                "pixelAspect": otio_clip_metadata["pixelAspect"]
            })
        else:
            otio_tl_metadata = context.data["otioTimeline"].metadata
            data.update({
                "resolutionWidth": otio_tl_metadata["width"],
                "resolutionHeight": otio_tl_metadata["height"],
                "pixelAspect": otio_tl_metadata["pixelAspect"]
            })

    def create_shot_instance(self, context, timeline_item, **data):
        hero_track = data.get("heroTrack")
        hierarchy_data = data.get("hierarchyData")

        if not hero_track:
            return

        if not hierarchy_data:
            return

        folder_path = data["folderPath"]
        product_name = "shotMain"

        # insert family into families
        product_type = "shot"

        data.update({
            "name": "{}_{}".format(folder_path, product_name),
            "label": "{} {}".format(folder_path, product_name),
            "folderPath": folder_path,
            "productName": product_name,
            "productType": product_type,
            "family": product_type,
            "families": [product_type],
            "publish": get_publish_attribute(timeline_item)
        })

        context.create_instance(**data)
