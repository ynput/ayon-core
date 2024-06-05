import ayon_api

from ayon_core.pipeline import get_representation_path
from ayon_core.lib.transcoding import (
    VIDEO_EXTENSIONS,
    IMAGE_EXTENSIONS
)
import ayon_hiero.api as phiero


class LoadClip(phiero.SequenceLoader):
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
    sequence = None
    track = None

    # presets
    clip_color_last = "green"
    clip_color = "red"

    clip_name_template = "{asset}_{subset}_{representation}"

    @classmethod
    def apply_settings(cls, project_settings):
        plugin_type_settings = (
            project_settings
            .get("hiero", {})
            .get("load", {})
        )

        if not plugin_type_settings:
            return

        plugin_name = cls.__name__

        # Look for plugin settings in host specific settings
        plugin_settings = plugin_type_settings.get(plugin_name)
        if not plugin_settings:
            return

        print(">>> We have preset for {}".format(plugin_name))
        for option, value in plugin_settings.items():
            if option == "representations":
                continue

            if option == "clip_name_template":
                # TODO remove the formatting replacement
                value = (
                    value
                    .replace("{folder[name]}", "{asset}")
                    .replace("{product[name]}", "{subset}")
                )

            if option == "enabled" and value is False:
                print("  - is disabled by preset")
            else:
                print("  - setting `{}`: `{}`".format(option, value))
            setattr(cls, option, value)

    def load(self, context, name, namespace, options):
        # add clip name template to options
        options.update({
            "clipNameTemplate": self.clip_name_template
        })
        # in case loader uses multiselection
        if self.track and self.sequence:
            options.update({
                "sequence": self.sequence,
                "track": self.track,
                "clipNameTemplate": self.clip_name_template
            })

        # load clip to timeline and get main variables
        path = self.filepath_from_context(context)
        track_item = phiero.ClipLoader(self, context, path, **options).load()
        namespace = namespace or track_item.name()
        version_entity = context["version"]
        version_attributes = version_entity["attrib"]
        version_name = version_entity["version"]
        colorspace = version_attributes.get("colorSpace")
        object_name = self.clip_name_template.format(
            **context["representation"]["context"])

        # set colorspace
        if colorspace:
            track_item.source().setSourceMediaColourTransform(colorspace)

        # add additional metadata from the version to imprint Avalon knob
        add_keys = [
            "frameStart", "frameEnd", "source", "author",
            "fps", "handleStart", "handleEnd"
        ]

        # move all version data keys to tag data
        data_imprint = {
            key: version_attributes.get(key, str(None))
            for key in add_keys

        }

        # add variables related to version context
        data_imprint.update({
            "version": version_name,
            "colorspace": colorspace,
            "objectName": object_name
        })

        # update color of clip regarding the version order
        self.set_item_color(
            context["project"]["name"], track_item, version_entity
        )

        # deal with multiselection
        self.multiselection(track_item)

        self.log.info("Loader done: `{}`".format(name))

        return phiero.containerise(
            track_item,
            name, namespace, context,
            self.__class__.__name__,
            data_imprint)

    def switch(self, container, context):
        self.update(container, context)

    def update(self, container, context):
        """ Updating previously loaded clips
        """
        version_entity = context["version"]
        repre_entity = context["representation"]

        # load clip to timeline and get main variables
        name = container["name"]
        namespace = container["namespace"]
        track_item = phiero.get_track_items(
            track_item_name=namespace).pop()

        version_attributes = version_entity["attrib"]
        version_name = version_entity["version"]
        colorspace = version_attributes.get("colorSpace")
        object_name = "{}_{}".format(name, namespace)

        file = get_representation_path(repre_entity).replace("\\", "/")
        clip = track_item.source()

        # reconnect media to new path
        clip.reconnectMedia(file)

        # set colorspace
        if colorspace:
            clip.setSourceMediaColourTransform(colorspace)

        # add additional metadata from the version to imprint metadata knob

        # move all version data keys to tag data
        data_imprint = {}
        for key in [
            "frameStart",
            "frameEnd",
            "source",
            "author",
            "fps",
            "handleStart",
            "handleEnd",
        ]:
            data_imprint.update({
                key: version_attributes.get(key, str(None))
            })

        # add variables related to version context
        data_imprint.update({
            "representation": repre_entity["id"],
            "version": version_name,
            "colorspace": colorspace,
            "objectName": object_name
        })

        # update color of clip regarding the version order
        self.set_item_color(
            context["project"]["name"], track_item, version_entity
        )

        return phiero.update_container(track_item, data_imprint)

    def remove(self, container):
        """ Removing previously loaded clips
        """
        # load clip to timeline and get main variables
        namespace = container['namespace']
        track_item = phiero.get_track_items(
            track_item_name=namespace).pop()
        track = track_item.parent()

        # remove track item from track
        track.removeItem(track_item)

    @classmethod
    def multiselection(cls, track_item):
        if not cls.track:
            cls.track = track_item.parent()
            cls.sequence = cls.track.parent()

    @classmethod
    def set_item_color(cls, project_name, track_item, version_entity):
        last_version_entity = ayon_api.get_last_version_by_product_id(
            project_name, version_entity["productId"], fields={"id"}
        )
        clip = track_item.source()
        # set clip colour
        if version_entity["id"] == last_version_entity["id"]:
            clip.binItem().setColor(cls.clip_color_last)
        else:
            clip.binItem().setColor(cls.clip_color)
