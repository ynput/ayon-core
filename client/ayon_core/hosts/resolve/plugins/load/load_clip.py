import ayon_api

from ayon_core.hosts.resolve.api import lib, plugin
from ayon_core.hosts.resolve.api.pipeline import (
    containerise,
    update_container,
)
from ayon_core.lib.transcoding import (
    VIDEO_EXTENSIONS,
    IMAGE_EXTENSIONS
)


class LoadClip(plugin.TimelineItemLoader):
    """Load a product to timeline as clip

    Place clip to timeline on its asset origin timings collected
    during conforming to project
    """

    product_types = {"render2d", "source", "plate", "render", "review"}

    representations = {"*"}
    extensions = set(
        ext.lstrip(".") for ext in IMAGE_EXTENSIONS.union(VIDEO_EXTENSIONS)
    )

    label = "Load as clip"
    order = -10
    icon = "code-fork"
    color = "orange"

    # for loader multiselection
    timeline = None

    # presets
    clip_color_last = "Olive"
    clip_color = "Orange"

    def load(self, context, name, namespace, options):

        # load clip to timeline and get main variables
        files = plugin.get_representation_files(context["representation"])

        timeline_item = plugin.ClipLoader(
            self, context, **options).load(files)
        namespace = namespace or timeline_item.GetName()

        # update color of clip regarding the version order
        self.set_item_color(
            context["project"]["name"],
            timeline_item,
            context["version"]
        )

        data_imprint = self.get_tag_data(context, name, namespace)
        return containerise(
            timeline_item,
            name, namespace, context,
            self.__class__.__name__,
            data_imprint)

    def switch(self, container, context):
        self.update(container, context)

    def update(self, container, context):
        """ Updating previously loaded clips
        """

        repre_entity = context["representation"]
        name = container['name']
        namespace = container['namespace']
        timeline_item = container["_timeline_item"]

        media_pool_item = timeline_item.GetMediaPoolItem()

        files = plugin.get_representation_files(repre_entity)

        loader = plugin.ClipLoader(self, context)
        timeline_item = loader.update(timeline_item, files)

        # update color of clip regarding the version order
        self.set_item_color(
            context["project"]["name"],
            timeline_item,
            context["version"]
        )

        # if original media pool item has no remaining usages left
        # remove it from the media pool
        if int(media_pool_item.GetClipProperty("Usage")) == 0:
            lib.remove_media_pool_item(media_pool_item)

        data_imprint = self.get_tag_data(context, name, namespace)
        return update_container(timeline_item, data_imprint)

    def get_tag_data(self, context, name, namespace):
        """Return data to be imprinted on the timeline item marker"""

        repre_entity = context["representation"]
        version_entity = context["version"]
        version_attributes = version_entity["attrib"]
        colorspace = version_attributes.get("colorSpace", None)
        object_name = "{}_{}".format(name, namespace)

        # add additional metadata from the version to imprint Avalon knob
        # move all version data keys to tag data
        add_version_data_keys = [
            "frameStart", "frameEnd", "source", "author",
            "fps", "handleStart", "handleEnd"
        ]
        data = {
            key: version_attributes.get(key, "None")
            for key in add_version_data_keys
        }

        # add variables related to version context
        data.update({
            "representation": repre_entity["id"],
            "version": version_entity["version"],
            "colorspace": colorspace,
            "objectName": object_name
        })
        return data

    @classmethod
    def set_item_color(cls, project_name, timeline_item, version_entity):
        """Color timeline item based on whether it is outdated or latest"""
        # get all versions in list
        last_version_entity = ayon_api.get_last_version_by_product_id(
            project_name,
            version_entity["productId"],
            fields=["name"]
        )
        last_version_id = None
        if last_version_entity:
            last_version_id = last_version_entity["id"]

        # set clip colour
        if version_entity["id"] == last_version_id:
            timeline_item.SetClipColor(cls.clip_color_last)
        else:
            timeline_item.SetClipColor(cls.clip_color)

    def remove(self, container):
        timeline_item = container["_timeline_item"]
        media_pool_item = timeline_item.GetMediaPoolItem()
        timeline = lib.get_current_timeline()

        # DeleteClips function was added in Resolve 18.5+
        # by checking None we can detect whether the
        # function exists in Resolve
        if timeline.DeleteClips is not None:
            timeline.DeleteClips([timeline_item])
        else:
            # Resolve versions older than 18.5 can't delete clips via API
            # so all we can do is just remove the pype marker to 'untag' it
            if lib.get_pype_marker(timeline_item):
                # Note: We must call `get_pype_marker` because
                # `delete_pype_marker` uses a global variable set by
                # `get_pype_marker` to delete the right marker
                # TODO: Improve code to avoid the global `temp_marker_frame`
                lib.delete_pype_marker(timeline_item)

        # if media pool item has no remaining usages left
        # remove it from the media pool
        if int(media_pool_item.GetClipProperty("Usage")) == 0:
            lib.remove_media_pool_item(media_pool_item)
