import os
import re
from ayon_core.pipeline.create import (
    Creator,
    CreatedInstance,
    get_product_name
)
from ayon_api import get_folder_by_path, get_task_by_name
from ayon_core.hosts.houdini.api import lib
import hou


def create_representation_data(files):
    """Create representation data needed for `instance.data['representations']"""
    first_file = files[0]
    folder, filename = os.path.split(first_file)

    # Files should be filename only in representation
    files = [os.path.basename(filepath) for filepath in files]

    ext = os.path.splitext(filename)[-1].strip(".")
    return {
        "name": ext,
        "ext": ext,
        "files": files if len(files) > 1 else filename,
        "stagingDir": folder,
    }


def create_file_list(match, start_frame, end_frame):
    """Collect files based on frame range and `regex.match`

    Args:
        match(re.match): match object
        start_frame(int): start of the animation
        end_frame(int): end of the animation

    Returns:
        list

    """

    # Get the padding length
    frame = match.group(1)
    padding = len(frame)

    # Get the parts of the filename surrounding the frame number,
    # so we can put our own frame numbers in.
    span = match.span(1)
    prefix = match.string[: span[0]]
    suffix = match.string[span[1]:]

    # Generate filenames for all frames
    result = []
    for i in range(start_frame, end_frame + 1):

        # Format frame number by the padding amount
        str_frame = "{number:0{width}d}".format(number=i, width=padding)

        file_name = prefix + str_frame + suffix
        result.append(file_name)

    return result


def eval_files_from_output_path(output_path, start_frame=None, end_frame=None):
    if start_frame is None:
        start_frame = hou.frame()

    if end_frame is None:
        end_frame = start_frame

    output = hou.expandStringAtFrame(output_path, start_frame)
    _, ext = lib.splitext(
        output, allowed_multidot_extensions=[
            ".ass.gz", ".bgeo.sc", ".bgeo.gz",
            ".bgeo.lzma", ".bgeo.bz2"])

    result = output
    pattern = r"\w+\.(\d+)" + re.escape(ext)
    match = re.match(pattern, output)

    if match and start_frame is not None:
        # Check if frames are bigger than 1 (file collection)
        # override the result
        if end_frame - start_frame > 0:
            result = create_file_list(
                match, int(start_frame), int(end_frame)
            )

    return result


class CreateRuntimeInstance(Creator):
    """Create in-memory instances for dynamic PDG publishing of files.

    These instances do not persist and are meant for headless automated
    publishing. The created instances are transient and will be gone on
    resetting the `CreateContext` since they will not be recollected.

    """
    # TODO: This should be a global HIDDEN creator instead!
    identifier = "io.openpype.creators.houdini.batch"
    label = "Ingest"
    product_type = "dynamic"  # not actually used
    icon = "gears"

    def create(self, product_name, instance_data, pre_create_data):

        # Unfortunately the Create Context will provide the product name
        # even before the `create` call without listening to pre create data
        # or the instance data - so instead we ignore the product name here
        # and redefine it ourselves based on the `variant` in instance data
        product_type = pre_create_data.get("product_type") or instance_data["product_type"]
        project_name = self.create_context.project_name
        folder_entity = get_folder_by_path(project_name,
                                           instance_data["folderPath"])
        task_entity = get_task_by_name(project_name,
                                       folder_id=folder_entity["id"],
                                       task_name=instance_data["task"])
        product_name = self._get_product_name_dynamic(
            self.create_context.project_name,
            folder_entity=folder_entity,
            task_entity=task_entity,
            variant=instance_data["variant"],
            product_type=product_type
        )

        custom_instance_data = pre_create_data.get("instance_data")
        if custom_instance_data:
            instance_data.update(custom_instance_data)

        instance_data["families"] = ["dynamic"]

        # TODO: Add support for multiple representations
        files = pre_create_data.get("files", [])
        if files:
            representations = [create_representation_data(files)]

        output_paths = pre_create_data.get("output_paths", [])
        if output_paths:
            representations = []
            for output_path in output_paths:
                files = eval_files_from_output_path(
                    output_path,
                    instance_data["frameStart"],
                    instance_data["frameEnd"])
                if isinstance(files, str):
                    files = [files]
                representation = create_representation_data(files)
                representation["frameStart"] = instance_data["frameStart"]
                representation["frameEnd"] = instance_data["frameEnd"]

                representations.append(representation)

        instance_data["representations"] = representations

        # We ingest it as a different product type then the creator's generic
        # ingest product type. For example, we specify `pointcache`
        instance = CreatedInstance(
            product_type=product_type,
            product_name=product_name,
            data=instance_data,
            creator=self
        )
        self._add_instance_to_context(instance)

        return instance

    # Instances are all dynamic at run-time and cannot be persisted or
    # re-collected
    def collect_instances(self):
        pass

    def update_instances(self, update_list):
        pass

    def remove_instances(self, instances):
        for instance in instances:
            self._remove_instance_from_context(instance)

    def _get_product_name_dynamic(
        self,
        project_name,
        folder_entity,
        task_entity,
        variant,
        product_type,
        host_name=None,
        instance=None
    ):
        """Implementation similar to `self.get_product_name` but taking
        `productType` as argument instead of using the 'generic' product type
        on the Creator itself."""
        if host_name is None:
            host_name = self.create_context.host_name

        task_name = task_type = None
        if task_entity:
            task_name = task_entity["name"]
            task_type = task_entity["taskType"]

        dynamic_data = self.get_dynamic_data(
            project_name,
            folder_entity,
            task_entity,
            variant,
            host_name,
            instance
        )

        return get_product_name(
            project_name,
            task_name,
            task_type,
            host_name,
            product_type,
            variant,
            dynamic_data=dynamic_data,
            project_settings=self.project_settings
        )
