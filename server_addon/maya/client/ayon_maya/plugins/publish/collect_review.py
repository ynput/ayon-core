import ayon_api
import pyblish.api
from ayon_core.pipeline import KnownPublishError
from ayon_maya.api import lib
from ayon_maya.api import plugin
from maya import cmds, mel


class CollectReview(plugin.MayaInstancePlugin):
    """Collect Review data

    """

    order = pyblish.api.CollectorOrder + 0.3
    label = 'Collect Review Data'
    families = ["review"]

    def process(self, instance):

        # Get panel.
        instance.data["panel"] = cmds.playblast(
            activeEditor=True
        ).rsplit("|", 1)[-1]

        # get cameras
        members = instance.data['setMembers']
        self.log.debug('members: {}'.format(members))
        cameras = cmds.ls(members, long=True, dag=True, cameras=True)
        camera = cameras[0] if cameras else None

        context = instance.context
        objectset = {
            i.data.get("instance_node") for i in context
        }

        # Collect display lights.
        display_lights = instance.data.get("displayLights", "default")
        if display_lights == "project_settings":
            settings = instance.context.data["project_settings"]
            settings = settings["maya"]["publish"]["ExtractPlayblast"]
            settings = settings["capture_preset"]["ViewportOptions"]
            display_lights = settings["displayLights"]

        # Collect camera focal length.
        burninDataMembers = instance.data.get("burninDataMembers", {})
        if camera is not None:
            attr = camera + ".focalLength"
            if lib.get_attribute_input(attr):
                start = instance.data["frameStart"]
                end = instance.data["frameEnd"] + 1
                time_range = range(int(start), int(end))
                focal_length = [cmds.getAttr(attr, time=t) for t in time_range]
            else:
                focal_length = cmds.getAttr(attr)

            burninDataMembers["focalLength"] = focal_length

        # Account for nested instances like model.
        reviewable_products = list(set(members) & objectset)
        if reviewable_products:
            if len(reviewable_products) > 1:
                raise KnownPublishError(
                    "Multiple attached products for review are not supported. "
                    "Attached: {}".format(", ".join(reviewable_products))
                )

            reviewable_product = reviewable_products[0]
            self.log.debug(
                "Product attached to review: {}".format(reviewable_product)
            )

            # Find the relevant publishing instance in the current context
            reviewable_inst = next(inst for inst in context
                                   if inst.name == reviewable_product)
            data = reviewable_inst.data

            self.log.debug(
                'Adding review family to {}'.format(reviewable_product)
            )
            if data.get('families'):
                data['families'].append('review')
            else:
                data['families'] = ['review']

            data["cameras"] = cameras
            data['review_camera'] = camera
            data['frameStartFtrack'] = instance.data["frameStartHandle"]
            data['frameEndFtrack'] = instance.data["frameEndHandle"]
            data['frameStartHandle'] = instance.data["frameStartHandle"]
            data['frameEndHandle'] = instance.data["frameEndHandle"]
            data['handleStart'] = instance.data["handleStart"]
            data['handleEnd'] = instance.data["handleEnd"]
            data["frameStart"] = instance.data["frameStart"]
            data["frameEnd"] = instance.data["frameEnd"]
            data['step'] = instance.data['step']
            # this (with other time related data) should be set on
            # representations. Once plugins like Extract Review start
            # using representations, this should be removed from here
            # as Extract Playblast is already adding fps to representation.
            data['fps'] = context.data['fps']
            data['review_width'] = instance.data['review_width']
            data['review_height'] = instance.data['review_height']
            data["isolate"] = instance.data["isolate"]
            data["panZoom"] = instance.data.get("panZoom", False)
            data["panel"] = instance.data["panel"]
            data["displayLights"] = display_lights
            data["burninDataMembers"] = burninDataMembers

            for key, value in instance.data["publish_attributes"].items():
                data["publish_attributes"][key] = value

            # The review instance must be active
            cmds.setAttr(str(instance) + '.active', 1)

            instance.data['remove'] = True

        else:
            project_name = instance.context.data["projectName"]
            folder_entity = instance.context.data["folderEntity"]
            task = instance.context.data["task"]
            legacy_product_name = task + 'Review'
            product_entity = ayon_api.get_product_by_name(
                project_name,
                legacy_product_name,
                folder_entity["id"],
                fields={"id"}
            )
            if product_entity:
                self.log.debug("Existing products found, keep legacy name.")
                instance.data["productName"] = legacy_product_name

            instance.data["cameras"] = cameras
            instance.data['review_camera'] = camera
            instance.data['frameStartFtrack'] = \
                instance.data["frameStartHandle"]
            instance.data['frameEndFtrack'] = \
                instance.data["frameEndHandle"]
            instance.data["displayLights"] = display_lights
            instance.data["burninDataMembers"] = burninDataMembers
            # this (with other time related data) should be set on
            # representations. Once plugins like Extract Review start
            # using representations, this should be removed from here
            # as Extract Playblast is already adding fps to representation.
            instance.data["fps"] = instance.context.data["fps"]

            # make ftrack publishable
            instance.data.setdefault("families", []).append('ftrack')

            cmds.setAttr(str(instance) + '.active', 1)

            # Collect audio
            playback_slider = mel.eval('$tmpVar=$gPlayBackSlider')
            audio_name = cmds.timeControl(playback_slider,
                                          query=True,
                                          sound=True)
            display_sounds = cmds.timeControl(
                playback_slider, query=True, displaySound=True
            )

            def get_audio_node_data(node):
                return {
                    "offset": cmds.getAttr("{}.offset".format(node)),
                    "filename": cmds.getAttr("{}.filename".format(node))
                }

            audio_data = []

            if audio_name:
                audio_data.append(get_audio_node_data(audio_name))

            elif display_sounds:
                start_frame = int(cmds.playbackOptions(query=True, min=True))
                end_frame = int(cmds.playbackOptions(query=True, max=True))

                for node in cmds.ls(type="audio"):
                    # Check if frame range and audio range intersections,
                    # for whether to include this audio node or not.
                    duration = cmds.getAttr("{}.duration".format(node))
                    start_audio = cmds.getAttr("{}.offset".format(node))
                    end_audio = start_audio + duration

                    if start_audio <= end_frame and end_audio > start_frame:
                        audio_data.append(get_audio_node_data(node))

            instance.data["audio"] = audio_data
