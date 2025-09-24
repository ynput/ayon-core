import os

from ayon_core.pipeline.create import (
    Creator,
    CreatedInstance,
    get_product_name
)
from ayon_api import get_folder_by_path, get_task_by_name


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
        "files": files if len(files) > 1 else first_file,
        "stagingDir": folder,
    }


class CreateRuntimeInstance(Creator):
    """Create in-memory instances for dynamic PDG publishing of files.

    These instances do not persist and are meant for headless automated
    publishing. The created instances are transient and will be gone on
    resetting the `CreateContext` since they will not be recollected.

    TODO: The goal is for this runtime instance to be so generic that it can
        run anywhere, globally - and needs no knowledge about its host. It's
        the simplest 'entry point' to ingesting something from anywhere.
        So it should have no Houdini or host-specific logic

    """
    # TODO: This should be a global HIDDEN creator instead!
    identifier = "io.openpype.creators.runtime_instance"
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

        # TODO: Add support for multiple representations
        files = pre_create_data["files"]
        representations = [create_representation_data(files)]
        instance_data["representations"] = representations
        instance_data["families"] = ["dynamic"]

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
