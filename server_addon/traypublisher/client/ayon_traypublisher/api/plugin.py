import ayon_api

from ayon_core.lib.attribute_definitions import (
    FileDef,
    BoolDef,
    NumberDef,
    UISeparatorDef,
)
from ayon_core.lib.transcoding import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from ayon_core.pipeline.create import (
    Creator,
    HiddenCreator,
    CreatedInstance,
    cache_and_get_instances,
    PRE_CREATE_THUMBNAIL_KEY,
)
from .pipeline import (
    list_instances,
    update_instances,
    remove_instances,
    HostContext,
)

REVIEW_EXTENSIONS = set(IMAGE_EXTENSIONS) | set(VIDEO_EXTENSIONS)
SHARED_DATA_KEY = "ayon.traypublisher.instances"


class HiddenTrayPublishCreator(HiddenCreator):
    host_name = "traypublisher"
    settings_category = "traypublisher"

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
        """Tray publisher specific method to store instance.

        Instance is stored into "workfile" of traypublisher and also add it
        to CreateContext.

        Args:
            new_instance (CreatedInstance): Instance that should be stored.
        """

        # Host implementation of storing metadata about instance
        HostContext.add_instance(new_instance.data_to_store())
        # Add instance to current context
        self._add_instance_to_context(new_instance)


class TrayPublishCreator(Creator):
    create_allow_context_change = True
    host_name = "traypublisher"
    settings_category = "traypublisher"

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
        """Tray publisher specific method to store instance.

        Instance is stored into "workfile" of traypublisher and also add it
        to CreateContext.

        Args:
            new_instance (CreatedInstance): Instance that should be stored.
        """

        # Host implementation of storing metadata about instance
        HostContext.add_instance(new_instance.data_to_store())
        new_instance.mark_as_stored()

        # Add instance to current context
        self._add_instance_to_context(new_instance)


class SettingsCreator(TrayPublishCreator):
    create_allow_context_change = True
    create_allow_thumbnail = True
    allow_version_control = False

    extensions = []

    def create(self, product_name, data, pre_create_data):
        # Pass precreate data to creator attributes
        thumbnail_path = pre_create_data.pop(PRE_CREATE_THUMBNAIL_KEY, None)

        # Fill 'version_to_use' if version control is enabled
        if self.allow_version_control:
            folder_path = data["folderPath"]
            product_entities_by_folder_path = self._prepare_next_versions(
                [folder_path], [product_name])
            version = product_entities_by_folder_path[folder_path].get(
                product_name
            )
            pre_create_data["version_to_use"] = version
            data["_previous_last_version"] = version

        data["creator_attributes"] = pre_create_data
        data["settings_creator"] = True

        # Create new instance
        new_instance = CreatedInstance(
            self.product_type, product_name, data, self
        )

        self._store_new_instance(new_instance)

        if thumbnail_path:
            self.set_instance_thumbnail_path(new_instance.id, thumbnail_path)

    def _prepare_next_versions(self, folder_paths, product_names):
        """Prepare next versions for given folder and product names.

        Todos:
            Expect combination of product names by folder path to avoid
                unnecessary server calls for unused products.

        Args:
            folder_paths (Iterable[str]): Folder paths.
            product_names (Iterable[str]): Product names.

        Returns:
            dict[str, dict[str, int]]: Last versions by fodler path
                and product names.
        """

        # Prepare all versions for all combinations to '1'
        # TODO use 'ayon_core.pipeline.version_start' logic
        product_entities_by_folder_path = {
            folder_path: {
                product_name: 1
                for product_name in product_names
            }
            for folder_path in folder_paths
        }
        if not folder_paths or not product_names:
            return product_entities_by_folder_path

        folder_entities = ayon_api.get_folders(
            self.project_name,
            folder_paths=folder_paths,
            fields={"id", "path"}
        )
        folder_paths_by_id = {
            folder_entity["id"]: folder_entity["path"]
            for folder_entity in folder_entities
        }
        product_entities = list(ayon_api.get_products(
            self.project_name,
            folder_ids=folder_paths_by_id.keys(),
            product_names=product_names,
            fields={"id", "name", "folderId"}
        ))

        product_ids = {p["id"] for p in product_entities}
        last_versions = ayon_api.get_last_versions(
            self.project_name,
            product_ids,
            fields={"version", "productId"})

        for product_entity in product_entities:
            product_id = product_entity["id"]
            product_name = product_entity["name"]
            folder_id = product_entity["folderId"]
            folder_path = folder_paths_by_id[folder_id]
            last_version = last_versions.get(product_id)
            version = 0
            if last_version is not None:
                version = last_version["version"]
            product_entities_by_folder_path[folder_path][product_name] += (
                version
            )
        return product_entities_by_folder_path

    def _fill_next_versions(self, instances_data):
        """Fill next version for instances.

        Instances have also stored previous next version to be able to
        recognize if user did enter different version. If version was
        not changed by user, or user set it to '0' the next version will be
        updated by current database state.
        """

        filtered_instance_data = []
        for instance in instances_data:
            previous_last_version = instance.get("_previous_last_version")
            creator_attributes = instance["creator_attributes"]
            use_next_version = creator_attributes.get(
                "use_next_version", True)
            version = creator_attributes.get("version_to_use", 0)
            if (
                use_next_version
                or version == 0
                or version == previous_last_version
            ):
                filtered_instance_data.append(instance)

        folder_paths = {
            instance["folderPath"]
            for instance in filtered_instance_data
        }
        product_names = {
            instance["productName"]
            for instance in filtered_instance_data}
        product_entities_by_folder_path = self._prepare_next_versions(
            folder_paths, product_names
        )
        for instance in filtered_instance_data:
            folder_path = instance["folderPath"]
            product_name = instance["productName"]
            version = product_entities_by_folder_path[folder_path][product_name]
            instance["creator_attributes"]["version_to_use"] = version
            instance["_previous_last_version"] = version

    def collect_instances(self):
        """Collect instances from host.

        Overriden to be able to manage version control attributes. If version
        control is disabled, the attributes will be removed from instances,
        and next versions are filled if is version control enabled.
        """

        instances_by_identifier = cache_and_get_instances(
            self, SHARED_DATA_KEY, list_instances
        )
        instances = instances_by_identifier[self.identifier]
        if not instances:
            return

        if self.allow_version_control:
            self._fill_next_versions(instances)

        for instance_data in instances:
            # Make sure that there are not data related to version control
            #   if plugin does not support it
            if not self.allow_version_control:
                instance_data.pop("_previous_last_version", None)
                creator_attributes = instance_data["creator_attributes"]
                creator_attributes.pop("version_to_use", None)
                creator_attributes.pop("use_next_version", None)

            instance = CreatedInstance.from_existing(instance_data, self)
            self._add_instance_to_context(instance)

    def get_instance_attr_defs(self):
        defs = self.get_pre_create_attr_defs()
        if self.allow_version_control:
            defs += [
                UISeparatorDef(),
                BoolDef(
                    "use_next_version",
                    default=True,
                    label="Use next version",
                ),
                NumberDef(
                    "version_to_use",
                    default=1,
                    minimum=0,
                    maximum=999,
                    label="Version to use",
                )
            ]
        return defs

    def get_pre_create_attr_defs(self):
        # Use same attributes as for instance attributes
        return [
            FileDef(
                "representation_files",
                folders=False,
                extensions=self.extensions,
                allow_sequences=self.allow_sequences,
                single_item=not self.allow_multiple_items,
                label="Representations",
            ),
            FileDef(
                "reviewable",
                folders=False,
                extensions=REVIEW_EXTENSIONS,
                allow_sequences=True,
                single_item=True,
                label="Reviewable representations",
                extensions_label="Single reviewable item"
            )
        ]

    @classmethod
    def from_settings(cls, item_data):
        identifier = item_data["identifier"]
        product_type = item_data["product_type"]
        if not identifier:
            identifier = "settings_{}".format(product_type)
        return type(
            "{}{}".format(cls.__name__, identifier),
            (cls, ),
            {
                "product_type": product_type,
                "identifier": identifier,
                "label": item_data["label"].strip(),
                "icon": item_data["icon"],
                "description": item_data["description"],
                "detailed_description": item_data["detailed_description"],
                "extensions": item_data["extensions"],
                "allow_sequences": item_data["allow_sequences"],
                "allow_multiple_items": item_data["allow_multiple_items"],
                "allow_version_control": item_data.get(
                    "allow_version_control", False),
                "default_variants": item_data["default_variants"],
            }
        )
