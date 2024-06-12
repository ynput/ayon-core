import re
import uuid

import qargparse

from ayon_core.pipeline.context_tools import get_current_project_asset

from ayon_core.lib import BoolDef

from ayon_core.pipeline import (
    LoaderPlugin,
    Creator as NewCreator
)

from ayon_core.pipeline.create import (
    Creator,
    HiddenCreator,
    CreatedInstance,
    cache_and_get_instances,
)

from .pipeline import (
    list_instances,
    update_instances,
    remove_instances,
    HostContext,
)

from . import lib, constants


SHARED_DATA_KEY = "ayon.resolve.instances"


class ClipLoader:

    active_bin = None
    data = {}

    def __init__(self, loader_obj, context, **options):
        """ Initialize object

        Arguments:
            loader_obj (ayon_core.pipeline.load.LoaderPlugin): plugin object
            context (dict): loader plugin context
            options (dict)[optional]: possible keys:
                projectBinPath: "path/to/binItem"

        """
        self.__dict__.update(loader_obj.__dict__)
        self.context = context
        self.active_project = lib.get_current_project()

        # try to get value from options or evaluate key value for `handles`
        self.with_handles = options.get("handles") is True

        # try to get value from options or evaluate key value for `load_to`
        self.new_timeline = (
            options.get("newTimeline") or
            options.get("load_to") == "New timeline"
        )
        # try to get value from options or evaluate key value for `load_how`
        self.sequential_load = (
            options.get("sequentially") or
            options.get("load_how") == "Sequentially in order"
        )

        assert self._populate_data(), str(
            "Cannot Load selected data, look into database "
            "or call your supervisor")

        # inject asset data to representation dict
        self._get_folder_attributes()

        # add active components to class
        if self.new_timeline:
            loader_cls = loader_obj.__class__
            if loader_cls.timeline:
                # if multiselection is set then use options sequence
                self.active_timeline = loader_cls.timeline
            else:
                # create new sequence
                self.active_timeline = lib.get_new_timeline(
                    "{}_{}".format(
                        self.data["timeline_basename"],
                        str(uuid.uuid4())[:8]
                    )
                )
                loader_cls.timeline = self.active_timeline

        else:
            self.active_timeline = lib.get_current_timeline()

    def _populate_data(self):
        """ Gets context and convert it to self.data
        data structure:
            {
                "name": "assetName_productName_representationName"
                "binPath": "projectBinPath",
            }
        """
        # create name
        folder_entity = self.context["folder"]
        product_name = self.context["product"]["name"]
        repre_entity = self.context["representation"]

        folder_name = folder_entity["name"]
        folder_path = folder_entity["path"]
        representation_name = repre_entity["name"]

        self.data["clip_name"] = "_".join([
            folder_name,
            product_name,
            representation_name
        ])
        self.data["versionAttributes"] = self.context["version"]["attrib"]

        self.data["timeline_basename"] = "timeline_{}_{}".format(
            product_name, representation_name)

        # solve project bin structure path
        hierarchy = "Loader{}".format(folder_path)

        self.data["binPath"] = hierarchy

        return True

    def _get_folder_attributes(self):
        """ Get all available asset data

        joint `data` key with asset.data dict into the representation

        """

        self.data["folderAttributes"] = copy.deepcopy(
            self.context["folder"]["attrib"]
        )

    def load(self, files):
        """Load clip into timeline

        Arguments:
            files (list[str]): list of files to load into timeline
        """
        # create project bin for the media to be imported into
        self.active_bin = lib.create_bin(self.data["binPath"])

        # create mediaItem in active project bin
        # create clip media
        media_pool_item = lib.create_media_pool_item(
            files,
            self.active_bin
        )
        _clip_property = media_pool_item.GetClipProperty
        source_in = int(_clip_property("Start"))
        source_out = int(_clip_property("End"))
        source_duration = int(_clip_property("Frames"))

        # Trim clip start if slate is present
        if "slate" in self.data["versionAttributes"]["families"]:
            source_in += 1
            source_duration = source_out - source_in + 1

        if not self.with_handles:
            # Load file without the handles of the source media
            # We remove the handles from the source in and source out
            # so that the handles are excluded in the timeline

            # get version data frame data from db
            version_attributes = self.data["versionAttributes"]
            frame_start = version_attributes.get("frameStart")
            frame_end = version_attributes.get("frameEnd")

            # The version data usually stored the frame range + handles of the
            # media however certain representations may be shorter because they
            # exclude those handles intentionally. Unfortunately the
            # representation does not store that in the database currently;
            # so we should compensate for those cases. If the media is shorter
            # than the frame range specified in the database we assume it is
            # without handles and thus we do not need to remove the handles
            # from source and out
            if frame_start is not None and frame_end is not None:
                # Version has frame range data, so we can compare media length
                handle_start = version_attributes.get("handleStart", 0)
                handle_end = version_attributes.get("handleEnd", 0)
                frame_start_handle = frame_start - handle_start
                frame_end_handle = frame_end + handle_end
                database_frame_duration = int(
                    frame_end_handle - frame_start_handle + 1
                )
                if source_duration >= database_frame_duration:
                    source_in += handle_start
                    source_out -= handle_end

        # get timeline in
        timeline_start = self.active_timeline.GetStartFrame()
        if self.sequential_load:
            # set timeline start frame
            timeline_in = int(timeline_start)
        else:
            # set timeline start frame + original clip in frame
            timeline_in = int(
                timeline_start + self.data["folderAttributes"]["clipIn"])

        # make track item from source in bin as item
        timeline_item = lib.create_timeline_item(
            media_pool_item,
            self.active_timeline,
            timeline_in,
            source_in,
            source_out,
        )

        print("Loading clips: `{}`".format(self.data["clip_name"]))
        return timeline_item

    def update(self, timeline_item, files):
        # create project bin for the media to be imported into
        self.active_bin = lib.create_bin(self.data["binPath"])

        # create mediaItem in active project bin
        # create clip media
        media_pool_item = lib.create_media_pool_item(
            files,
            self.active_bin
        )
        _clip_property = media_pool_item.GetClipProperty

        # Read trimming from timeline item
        timeline_item_in = timeline_item.GetLeftOffset()
        timeline_item_len = timeline_item.GetDuration()
        timeline_item_out = timeline_item_in + timeline_item_len

        lib.swap_clips(
            timeline_item,
            media_pool_item,
            timeline_item_in,
            timeline_item_out
        )

        print("Loading clips: `{}`".format(self.data["clip_name"]))
        return timeline_item


class TimelineItemLoader(LoaderPlugin):
    """A basic SequenceLoader for Resolve

    This will implement the basic behavior for a loader to inherit from that
    will containerize the reference and will implement the `remove` and
    `update` logic.

    """

    options = [
        qargparse.Boolean(
            "handles",
            label="Include handles",
            default=0,
            help="Load with handles or without?"
        ),
        qargparse.Choice(
            "load_to",
            label="Where to load clips",
            items=[
                "Current timeline",
                "New timeline"
            ],
            default=0,
            help="Where do you want clips to be loaded?"
        ),
        qargparse.Choice(
            "load_how",
            label="How to load clips",
            items=[
                "Original timing",
                "Sequentially in order"
            ],
            default="Original timing",
            help="Would you like to place it at original timing?"
        )
    ]

    def load(
        self,
        context,
        name=None,
        namespace=None,
        options=None
    ):
        pass

    def update(self, container, context):
        """Update an existing `container`
        """
        pass

    def remove(self, container):
        """Remove an existing `container`
        """
        pass


class ResolveCreator(NewCreator):
    """ Resolve Creator class wrapper"""

    marker_color = "Purple"
    presets = {}

    def apply_settings(self, project_settings):
        resolve_create_settings = (
            project_settings.get("resolve", {}).get("create")
        )
        self.presets = resolve_create_settings.get(
            self.__class__.__name__, {}
        )

    def create(self, subset_name, instance_data, pre_create_data):
        # adding basic current context resolve objects
        self.project = lib.get_current_resolve_project()
        self.timeline = lib.get_current_timeline()

        if pre_create_data.get("use_selection", False):
            self.selected = lib.get_current_timeline_items(filter=True)
        else:
            self.selected = lib.get_current_timeline_items(filter=False)

        # TODO: Add a way to store/imprint data

    def get_pre_create_attr_defs(self):
        return [
            BoolDef("use_selection",
                    label="Use selection",
                    default=True)
        ]

# alias for backward compatibility
Creator = ResolveCreator  # noqa


class PublishableClip:
    """
    Convert a track item to publishable instance
    """
    types = {
        "shot": "shot",
        "folder": "folder",
        "episode": "episode",
        "sequence": "sequence",
        "track": "sequence",
    }

    # parents search pattern
    parents_search_pattern = r"\{([a-z]*?)\}"

    # default templates for non-ui use
    rename_default = False
    hierarchy_default = "{_folder_}/{_sequence_}/{_track_}"
    clip_name_default = "shot_{_trackIndex_:0>3}_{_clipIndex_:0>4}"
    variant_default = "<track_name>"
    review_track_default = "< none >"
    product_type_default = "plate"
    count_from_default = 10
    count_steps_default = 10
    vertical_sync_default = False
    driving_layer_default = ""

    # Define which keys of the pre create data should also be 'tag data'
    tag_keys = {
        # renameHierarchy
        "hierarchy",
        # hierarchyData
        "folder", "episode", "sequence", "track", "shot",
        # publish settings
        "audio", "sourceResolution",
        # shot attributes
        "workfileFrameStart", "handleStart", "handleEnd"
    }

    def __init__(
            self,
            timeline_item_data: dict,
            pre_create_data: dict = None,
            media_pool_folder: str = None,
            rename_index: int = 0,
            data: dict = None
        ):
        """ Initialize object

        Args:
            timeline_item_data (dict): timeline item data
            pre_create_data (dict): pre create data
            media_pool_folder (str): media pool folder
            rename_index (int): rename index
            data (dict): additional data

        """
        self.rename_index = rename_index
        self.vertical_clip_match = {}
        self.tag_data = data or {}

        # get main parent objects
        self.timeline_item_data = timeline_item_data
        self.timeline_item = timeline_item_data["clip"]["item"]
        timeline_name = timeline_item_data["timeline"].GetName()
        self.timeline_name = str(timeline_name).replace(" ", "_")

        # track item (clip) main attributes
        self.ti_name = self.timeline_item.GetName()
        self.ti_index = int(timeline_item_data["clip"]["index"])

        # get track name and index
        track_name = timeline_item_data["track"]["name"]
        self.track_name = str(track_name).replace(" ", "_")
        self.track_index = int(timeline_item_data["track"]["index"])

        # adding ui inputs if any
        self.pre_create_data = pre_create_data or {}

        # adding media pool folder if any
        self.media_pool_folder = media_pool_folder

        # populate default data before we get other attributes
        self._populate_timeline_item_default_data()

        # use all populated default data to create all important attributes
        self._populate_attributes()

        # create parents with correct types
        self._create_parents()

    def convert(self):
        """ Convert track item to publishable instance.

        Returns:
            timeline_item (resolve.TimelineItem): timeline item with imprinted
                data in marker
        """
        # solve track item data and add them to tag data
        self._convert_to_tag_data()

        # if track name is in review track name and also if driving track name
        # is not in review track name: skip tag creation
        if (
            self.track_name in self.review_track and
            self.hero_track not in self.review_track
        ):
            return

        # deal with clip name
        new_name = self.tag_data.pop("newClipName")

        if self.rename:
            self.tag_data["asset"] = new_name
        else:
            self.tag_data["asset"] = self.ti_name

        if not constants.ayon_marker_workflow:
            # create compound clip workflow
            lib.create_compound_clip(
                self.timeline_item_data,
                self.tag_data["asset"],
                self.media_pool_folder
            )

            # add timeline_item_data selection to tag
            self.tag_data.update({
                "track_data": self.timeline_item_data["track"]
            })

        # create openpype tag on timeline_item and add data
        lib.imprint(self.timeline_item, self.tag_data)

        return self.timeline_item

    def _populate_timeline_item_default_data(self):
        """ Populate default formatting data from track item. """

        self.timeline_item_default_data = {
            "_folder_": "shots",
            "_sequence_": self.timeline_name,
            "_track_": self.track_name,
            "_clip_": self.ti_name,
            "_trackIndex_": self.track_index,
            "_clipIndex_": self.ti_index
        }

    def _populate_attributes(self):
        """ Populate main object attributes. """
        # track item frame range and parent track name for vertical sync check
        self.clip_in = int(self.timeline_item.GetStart())
        self.clip_out = int(self.timeline_item.GetEnd())

        # define ui inputs if non gui mode was used
        self.shot_num = self.ti_index

        # publisher ui attribute inputs or default values if gui was not used
        def get(key):
            """Shorthand access for code readability"""
            return self.pre_create_data.get(key)

        self.rename = get("clipRename") or self.rename_default
        self.clip_name = get("clipName") or self.clip_name_default
        self.hierarchy = get("hierarchy") or self.hierarchy_default
        self.count_from = get("countFrom") or self.count_from_default
        self.count_steps = get("countSteps") or self.count_steps_default
        self.variant = get("variant") or self.variant_default
        self.product_type = get("productType") or self.product_type_default
        self.vertical_sync = get("vSyncOn") or self.vertical_sync_default
        self.hero_track = get("vSyncTrack") or self.driving_layer_default
        self.review_media_track = (
            get("reviewTrack") or self.review_track_default)

        self.hierarchy_data = {
            key: get(key) or self.timeline_item_default_data[key]
            for key in ["folder", "episode", "sequence", "track", "shot"]
        }

        # build subset name from layer name
        if self.variant == "<track_name>":
            self.variant = self.track_name

        # create subset for publishing
        # TODO: Use creator `get_subset_name` to correctly define name
        self.product_name = self.product_type + self.variant.capitalize()

    def _replace_hash_to_expression(self, name, text):
        """ Replace hash with number in correct padding. """
        _spl = text.split("#")
        _len = (len(_spl) - 1)
        _repl = "{{{0}:0>{1}}}".format(name, _len)
        new_text = text.replace(("#" * _len), _repl)
        return new_text

    def _convert_to_tag_data(self):
        """Convert internal data to tag data.

        Populating the tag data into internal variable self.tag_data
        """
        # define vertical sync attributes
        hero_track = True
        self.review_track = ""

        if self.vertical_sync and self.track_name not in self.hero_track:
            hero_track = False

        # increasing steps by index of rename iteration
        self.count_steps *= self.rename_index

        hierarchy_formatting_data = {}
        _data = self.timeline_item_default_data.copy()
        if self.pre_create_data:

            # adding tag metadata from ui
            for _key, _value in self.pre_create_data.items():
                if _key in self.tag_keys:
                    self.tag_data[_key] = _value

            # driving layer is set as positive match
            if hero_track or self.vertical_sync:
                # mark review track
                if (
                    self.review_media_track
                    and self.review_media_track not in self.review_track_default  # noqa
                ):
                    # if review track is defined and not the same as default
                    self.review_track = self.review_media_track
                # shot num calculate
                if self.rename_index == 0:
                    self.shot_num = self.count_from
                else:
                    self.shot_num = self.count_from + self.count_steps

            # clip name sequence number
            _data.update({"shot": self.shot_num})

            # solve # in test to pythonic expression
            for _key, _value in self.hierarchy_data.items():
                if "#" not in _value:
                    continue
                self.hierarchy_data[_key] = self._replace_hash_to_expression(
                    _key, _value
                )

            # fill up pythonic expresisons in hierarchy data
            for _key, _value in self.hierarchy_data.items():
                hierarchy_formatting_data[_key] = _value.format(**_data)
        else:
            # if no gui mode then just pass default data
            hierarchy_formatting_data = self.hierarchy_data

        tag_hierarchy_data = self._solve_tag_hierarchy_data(
            hierarchy_formatting_data
        )

        tag_hierarchy_data.update({"heroTrack": True})
        if hero_track and self.vertical_sync:
            self.vertical_clip_match.update({
                (self.clip_in, self.clip_out): tag_hierarchy_data
            })

        if not hero_track and self.vertical_sync:
            # driving layer is set as negative match
            for (_in, _out), hero_data in self.vertical_clip_match.items():
                hero_data.update({"heroTrack": False})
                if _in == self.clip_in and _out == self.clip_out:
                    data_subset = hero_data["product_name"]
                    # add track index in case duplicity of names in hero data
                    if self.product_name in data_subset:
                        hero_data["product_name"] = self.product_name + str(
                            self.track_index)
                    # in case track name and subset name is the same then add
                    if self.variant == self.track_name:
                        hero_data["product_name"] = self.product_name
                    # assign data to return hierarchy data to tag
                    tag_hierarchy_data = hero_data

        # add data to return data dict
        self.tag_data.update(tag_hierarchy_data)

        # add uuid to tag data
        self.tag_data["uuid"] = str(uuid.uuid4())

        # add review track only to hero track
        if hero_track and self.review_track:
            self.tag_data.update({"reviewTrack": self.review_track})
        else:
            self.tag_data.update({"reviewTrack": None})

    def _solve_tag_hierarchy_data(self, hierarchy_formatting_data):
        """ Solve tag data from hierarchy data and templates. """
        # fill up clip name and hierarchy keys
        hierarchy_filled = self.hierarchy.format(**hierarchy_formatting_data)
        clip_name_filled = self.clip_name.format(**hierarchy_formatting_data)

        return {
            "newClipName": clip_name_filled,
            "hierarchy": hierarchy_filled,
            "parents": self.parents,
            "hierarchyData": hierarchy_formatting_data,
            "productName": self.product_name,
            "productType": self.product_type
        }

    def _convert_to_entity(self, key):
        """ Converting input key to key with type. """
        # convert to entity type
        folder_type = self.types.get(key)

        assert folder_type, "Missing folder type for `{}`".format(
            key
        )

        return {
            "folder_type": folder_type,
            "entity_name": self.hierarchy_data[key]["value"].format(
                **self.timeline_item_default_data
            )
        }

    def _create_parents(self):
        """ Create parents and return it in list. """
        self.parents = []

        pattern = re.compile(self.parents_search_pattern)
        par_split = [pattern.findall(t).pop()
                     for t in self.hierarchy.split("/")]

        for key in par_split:
            parent = self._convert_to_entity(key)
            self.parents.append(parent)

# alias for backward compatibility
PublishClip = PublishableClip  # noqa


class HiddenResolvePublishCreator(HiddenCreator):
    host_name = "resolve"
    settings_category = "resolve"

    def collect_instances(self):
        instances_by_identifier = cache_and_get_instances(
            self, SHARED_DATA_KEY, list_instances
        )
        for instance_data in instances_by_identifier[self.identifier]:
            instance = CreatedInstance.from_existing(instance_data, self)
            self._add_instance_to_context(instance)

    def update_instances(self, update_list):
        update_instances(update_list)

    def remove_instances(self, instances):
        remove_instances(instances)
        for instance in instances:
            self._remove_instance_from_context(instance)

    def _store_new_instance(self, new_instance):
        """Resolve publisher specific method to store instance.

        Instance is stored into "workfile" of Resolve and also add it
        to CreateContext.

        Args:
            new_instance (CreatedInstance): Instance that should be stored.
        """

        # Host implementation of storing metadata about instance
        HostContext.add_instance(new_instance.data_to_store())
        # Add instance to current context
        self._add_instance_to_context(new_instance)


class ResolvePublishCreator(Creator):
    create_allow_context_change = True
    host_name = "resolve"
    settings_category = "resolve"

    def collect_instances(self):
        instances_by_identifier = cache_and_get_instances(
            self, SHARED_DATA_KEY, list_instances
        )
        for instance_data in instances_by_identifier[self.identifier]:
            instance = CreatedInstance.from_existing(instance_data, self)
            self._add_instance_to_context(instance)

    def update_instances(self, update_list):
        update_instances(update_list)

    def remove_instances(self, instances):
        remove_instances(instances)
        for instance in instances:
            self._remove_instance_from_context(instance)

    def _store_new_instance(self, new_instance):
        """Resolve publisher specific method to store instance.

        Instance is stored into "workfile" of Resolve and also add it
        to CreateContext.

        Args:
            new_instance (CreatedInstance): Instance that should be stored.
        """

        # Host implementation of storing metadata about instance
        HostContext.add_instance(new_instance.data_to_store())
        new_instance.mark_as_stored()

        # Add instance to current context
        self._add_instance_to_context(new_instance)
