import pyblish.api

import ayon_flame.api as opfapi
from ayon_flame.otio import flame_export
from ayon_core.pipeline.create import get_product_name


class CollecTimelineOTIO(pyblish.api.ContextPlugin):
    """Inject the current working context into publish context"""

    label = "Collect Timeline OTIO"
    order = pyblish.api.CollectorOrder - 0.099

    def process(self, context):
        # plugin defined
        product_type = "workfile"
        variant = "otioTimeline"

        # main
        folder_entity = context.data["folderEntity"]
        project = opfapi.get_current_project()
        sequence = opfapi.get_current_sequence(opfapi.CTX.selection)

        # create product name
        task_entity = context.data["taskEntity"]
        task_name = task_type = None
        if task_entity:
            task_name = task_entity["name"]
            task_type = task_entity["taskType"]
        product_name = get_product_name(
            context.data["projectName"],
            task_name,
            task_type,
            context.data["hostName"],
            product_type,
            variant,
            project_settings=context.data["project_settings"]
        )

        # adding otio timeline to context
        with opfapi.maintained_segment_selection(sequence) as selected_seg:
            otio_timeline = flame_export.create_otio_timeline(sequence)

            instance_data = {
                "name": product_name,
                "folderPath": folder_entity["path"],
                "productName": product_name,
                "productType": product_type,
                "family": product_type,
                "families": [product_type]
            }

            # create instance with workfile
            instance = context.create_instance(**instance_data)
            self.log.info("Creating instance: {}".format(instance))

            # update context with main project attributes
            context.data.update({
                "flameProject": project,
                "flameSequence": sequence,
                "otioTimeline": otio_timeline,
                "currentFile": "Flame/{}/{}".format(
                    project.name, sequence.name
                ),
                "flameSelectedSegments": selected_seg,
                "fps": float(str(sequence.frame_rate)[:-4])
            })
