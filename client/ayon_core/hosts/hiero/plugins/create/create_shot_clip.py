import copy

from ayon_core.hosts.hiero.api import plugin, lib
# from ayon_core.hosts.hiero.api import plugin, lib
# reload(lib)
# reload(plugin)
# reload(phiero)

from ayon_core.pipeline.create import CreatorError, CreatedInstance
from ayon_core.lib import BoolDef, EnumDef, TextDef, UILabelDef, NumberDef


class CreateShotClip(plugin.HieroCreator):
    """Publishable clip"""

    identifier = "io.openpype.creators.hiero.clip"
    label = "Create Publishable Clip"
    family = "clip"
    icon = "film"
    defaults = ["Main"]

    create_allow_context_change = False
    create_allow_thumbnail = False

    def get_pre_create_attr_defs(self):

        def header_label(text):
            return f"<br><b>{text}</b>"

        tokens_help = """\nUsable tokens:
    {_clip_}: name of used clip
    {_track_}: name of parent track layer
    {_sequence_}: name of parent sequence (timeline)"""
        # gui_name = "OpenPype publish attributes creator"
        # gui_info = "Define sequential rename and fill hierarchy data."
        gui_tracks = [track.name()
            for track in lib.get_current_sequence().videoTracks()]

        # Project settings might be applied to this creator via
        # the inherited `Creator.apply_settings`
        presets = self.presets

        return [

            BoolDef("use_selection",
                    label="Use only clips with <b>Chocolate</b>  clip color",
                    tooltip=(
                        "When enabled only clips of Chocolate clip color are "
                        "considered.\n\n"
                        "Acts as a replacement to 'Use selection' because "
                        "Resolves API exposes no functionality to retrieve "
                        "the currently selected timeline items."
                    ),
                    default=True),

            # renameHierarchy
            UILabelDef(
                label=header_label("Shot Hierarchy And Rename Settings")
            ),
            TextDef(
                "hierarchy",
                label="Shot Parent Hierarchy",
                tooltip="Parents folder for shot root folder, "
                        "Template filled with *Hierarchy Data* section",
                default=presets.get("hierarchy", "{folder}/{sequence}"),
            ),
            BoolDef(
                "clipRename",
                label="Rename clips",
                tooltip="Renaming selected clips on fly",
                default=presets.get("clipRename", False),
            ),
            TextDef(
                "clipName",
                label="Clip Name Template",
                tooltip="template for creating shot names, used for "
                        "renaming (use rename: on)",
                default=presets.get("clipName", "{sequence}{shot}"),
            ),
            NumberDef(
                "countFrom",
                label="Count sequence from",
                tooltip="Set where the sequence number starts from",
                default=presets.get("countFrom", 10),
            ),
            NumberDef(
                "countSteps",
                label="Stepping number",
                tooltip="What number is adding every new step",
                default=presets.get("countSteps", 10),
            ),

            # hierarchyData
            UILabelDef(
                label=header_label("Shot Template Keywords")
            ),
            TextDef(
                "folder",
                label="{folder}",
                tooltip="Name of folder used for root of generated shots.\n"
                        f"{tokens_help}",
                default=presets.get("folder", "shots"),
            ),
            TextDef(
                "episode",
                label="{episode}",
                tooltip=f"Name of episode.\n{tokens_help}",
                default=presets.get("episode", "ep01"),
            ),
            TextDef(
                "sequence",
                label="{sequence}",
                tooltip=f"Name of sequence of shots.\n{tokens_help}",
                default=presets.get("sequence", "sq01"),
            ),
            TextDef(
                "track",
                label="{track}",
                tooltip=f"Name of timeline track.\n{tokens_help}",
                default=presets.get("track", "{_track_}"),
            ),
            TextDef(
                "shot",
                label="{shot}",
                tooltip="Name of shot. '#' is converted to padded number."
                        f"\n{tokens_help}",
                default=presets.get("shot", "sh###"),
            ),

            # verticalSync
            UILabelDef(
                label=header_label("Vertical Synchronization Of Attributes")
            ),
            BoolDef(
                "vSyncOn",
                label="Enable Vertical Sync",
                tooltip="Switch on if you want clips above "
                        "each other to share its attributes",
                default=presets.get("vSyncOn", True),
            ),
            EnumDef(
                "vSyncTrack",
                label="Hero track",
                tooltip="Select driving track name which should "
                        "be mastering all others",
                items=gui_tracks or ["<nothing to select>"],
            ),

            # publishSettings
            UILabelDef(
                label=header_label("Publish Settings")
            ),
            EnumDef(
                "subsetName",
                label="Subset Name",
                tooltip="chose subset name pattern, if <track_name> "
                        "is selected, name of track layer will be used",
                items=['<track_name>', 'main', 'bg', 'fg', 'bg', 'animatic'],
            ),
            EnumDef(
                "subsetFamily",
                label="Subset Family",
                tooltip="What use of this subset is for",
                items=['plate', 'take'],
            ),
            EnumDef(
                "reviewTrack",
                label="Use Review Track",
                tooltip="Generate preview videos on fly, if "
                        "'< none >' is defined nothing will be generated.",
                items=['< none >'] + gui_tracks,
            ),
            BoolDef(
                "audio",
                label="Include audio",
                tooltip="Process subsets with corresponding audio",
                default=False,
            ),
            BoolDef(
                "sourceResolution",
                label="Source resolution",
                tooltip="Is resloution taken from timeline or source?",
                default=False,
            ),

            # shotAttr
            UILabelDef(
                label=header_label("Shot Attributes"),
            ),
            NumberDef(
                "workfileFrameStart",
                label="Workfiles Start Frame",
                tooltip="Set workfile starting frame number",
                default=presets.get("workfileFrameStart", 1001),
            ),
            NumberDef(
                "handleStart",
                label="Handle start (head)",
                tooltip="Handle at start of clip",
                default=presets.get("handleStart", 0),
            ),
            NumberDef(
                "handleEnd",
                label="Handle end (tail)",
                tooltip="Handle at end of clip",
                default=presets.get("handleEnd", 0),
            ),
        ]

    presets = None
    rename_index = 0

    def create(self, subset_name, instance_data, pre_create_data):
        super(CreateShotClip, self).create(subset_name,
                                           instance_data,
                                           pre_create_data)

        if len(self.selected) < 1:
            return

        self.log.info(self.selected)

        self.log.debug(f"Selected: {self.selected}")

        # get ui output for track name for vertical sync

        # sort selected trackItems by
        sorted_selected_track_items = list()
        unsorted_selected_track_items = list()
        v_sync_track = pre_create_data.get("vSyncTrack", "")
        for _ti in self.selected:
            if _ti.parent().name() in v_sync_track:
                sorted_selected_track_items.append(_ti)
            else:
                unsorted_selected_track_items.append(_ti)

        sorted_selected_track_items.extend(unsorted_selected_track_items)

        instances = []
        for i, track_item in enumerate(sorted_selected_track_items):

            # convert track item to timeline media pool item
            publish_clip = plugin.PublishClip(
                track_item,
                pre_create_data=pre_create_data,
                rename_index=i,
                avalon=instance_data)

            track_item = publish_clip.convert()
            if track_item is None:
                # Ignore input clips that do not convert into a track item
                # from `PublishClip.convert`
                continue

            instance_data = copy.deepcopy(instance_data)
            # TODO: set 'task', 'family' and 'variant' correctly
            #  and build its subset name correctly
            # TODO: We can't set the asset because the asset does not exist
            #   and the new publisher doesn't like non-existing assets
            # instance_data["asset"] = publish_clip.tag_data["asset"]
            # instance_data["variant"] = publish_clip.subset_name

            # Create the Publisher instance
            instance = CreatedInstance(
                family=self.family,
                subset_name=publish_clip.subset_name,
                data=instance_data,
                creator=self
            )
            instance.transient_data["track_item"] = track_item
            self._add_instance_to_context(instance)

            # self.imprint_instance_node(instance_node,
            #                            data=instance.data_to_store())
            instances.append(instance)
        return instances

    def collect_instances(self):
        """Collect all created instances from current timeline."""

        # TODO: is this really what we want to do here...
        gui_tracks = [track for track in lib.get_current_sequence().videoTracks()]

        instances = []
        for track_item in gui_tracks:

            # get openpype tag data
            tag_data = lib.get_trackitem_openpype_tag(track_item)
            if not tag_data:
                continue

            instance = CreatedInstance.from_existing(tag_data, self)
            instance.transient_data["track_item"] = track_item
            self._add_instance_to_context(instance)

            print("ZZ", tag_data)

        return instances

    def update_instances(self, update_list):
        """Store changes of existing instances so they can be recollected.

        Args:
            update_list(List[UpdateData]): Gets list of tuples. Each item
                contain changed instance and it's changes.
        """
        for created_inst, _changes in update_list:
            track_item = created_inst.transient_data["track_item"]
            data = created_inst.data_to_store()
            self.log.info(f"Storing data: {data}")

            lib.imprint(track_item, data)

    def remove_instances(self, instances):
        """Remove instance marker from track item.

        Args:
            instance(List[CreatedInstance]): Instance objects which should be
                removed.
        """
        for instance in instances:
            track_item = instance.transient_data["track_item"]

            # removing instance by marker color
            print(f"Removing instance: {track_item.GetName()}")
            # TODO: Do something in host app?
            # track_item.DeleteMarkersByColor(lib.pype_marker_color)

            self._remove_instance_from_context(instance)