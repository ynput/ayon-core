import logging
import re
from typing import Union, List, Dict, Tuple, Any, Optional, Iterable, Pattern

from ayon_core.lib.attribute_definitions import (
    serialize_attr_defs,
    deserialize_attr_defs,
    AbstractAttrDef,
)
from ayon_core.lib.profiles_filtering import filter_profiles
from ayon_core.lib.attribute_definitions import UIDef
from ayon_core.lib import is_func_signature_supported
from ayon_core.pipeline.create import (
    BaseCreator,
    AutoCreator,
    HiddenCreator,
    Creator,
    CreateContext,
    CreatedInstance,
)
from ayon_core.pipeline.create import (
    CreatorsOperationFailed,
    ConvertorsOperationFailed,
    ConvertorItem,
)
from ayon_core.tools.publisher.abstract import (
    AbstractPublisherBackend,
    CardMessageTypes,
)

CREATE_EVENT_SOURCE = "publisher.create.model"


class CreatorType:
    def __init__(self, name: str):
        self.name: str = name

    def __str__(self):
        return self.name

    def __eq__(self, other):
        return self.name == str(other)

    def __ne__(self, other):
        # This is implemented only because of Python 2
        return not self == other


class CreatorTypes:
    base = CreatorType("base")
    auto = CreatorType("auto")
    hidden = CreatorType("hidden")
    artist = CreatorType("artist")

    @classmethod
    def from_str(cls, value: str) -> CreatorType:
        for creator_type in (
            cls.base,
            cls.auto,
            cls.hidden,
            cls.artist
        ):
            if value == creator_type:
                return creator_type
        raise ValueError("Unknown type \"{}\"".format(str(value)))


class CreatorItem:
    """Wrapper around Creator plugin.

    Object can be serialized and recreated.
    """

    def __init__(
        self,
        identifier: str,
        creator_type: CreatorType,
        product_type: str,
        label: str,
        group_label: str,
        icon: Union[str, Dict[str, Any], None],
        description: Union[str, None],
        detailed_description: Union[str, None],
        default_variant: Union[str, None],
        default_variants: Union[List[str], None],
        create_allow_context_change: Union[bool, None],
        create_allow_thumbnail: Union[bool, None],
        show_order: int,
        pre_create_attributes_defs: List[AbstractAttrDef],
    ):
        self.identifier: str = identifier
        self.creator_type: CreatorType = creator_type
        self.product_type: str = product_type
        self.label: str = label
        self.group_label: str = group_label
        self.icon: Union[str, Dict[str, Any], None] = icon
        self.description: Union[str, None] = description
        self.detailed_description: Union[bool, None] = detailed_description
        self.default_variant: Union[bool, None] = default_variant
        self.default_variants: Union[List[str], None] = default_variants
        self.create_allow_context_change: Union[bool, None] = (
            create_allow_context_change
        )
        self.create_allow_thumbnail: Union[bool, None] = create_allow_thumbnail
        self.show_order: int = show_order
        self.pre_create_attributes_defs: List[AbstractAttrDef] = (
            pre_create_attributes_defs
        )

    def get_group_label(self) -> str:
        return self.group_label

    @classmethod
    def from_creator(cls, creator: BaseCreator):
        creator_type: CreatorType = CreatorTypes.base
        if isinstance(creator, AutoCreator):
            creator_type = CreatorTypes.auto
        elif isinstance(creator, HiddenCreator):
            creator_type = CreatorTypes.hidden
        elif isinstance(creator, Creator):
            creator_type = CreatorTypes.artist

        description = None
        detail_description = None
        default_variant = None
        default_variants = None
        pre_create_attr_defs = None
        create_allow_context_change = None
        create_allow_thumbnail = None
        show_order = creator.order
        if creator_type is CreatorTypes.artist:
            description = creator.get_description()
            detail_description = creator.get_detail_description()
            default_variant = creator.get_default_variant()
            default_variants = creator.get_default_variants()
            pre_create_attr_defs = creator.get_pre_create_attr_defs()
            create_allow_context_change = creator.create_allow_context_change
            create_allow_thumbnail = creator.create_allow_thumbnail
            show_order = creator.show_order

        identifier = creator.identifier
        return cls(
            identifier,
            creator_type,
            creator.product_type,
            creator.label or identifier,
            creator.get_group_label(),
            creator.get_icon(),
            description,
            detail_description,
            default_variant,
            default_variants,
            create_allow_context_change,
            create_allow_thumbnail,
            show_order,
            pre_create_attr_defs,
        )

    def to_data(self) -> Dict[str, Any]:
        pre_create_attributes_defs = None
        if self.pre_create_attributes_defs is not None:
            pre_create_attributes_defs = serialize_attr_defs(
                self.pre_create_attributes_defs
            )

        return {
            "identifier": self.identifier,
            "creator_type": str(self.creator_type),
            "product_type": self.product_type,
            "label": self.label,
            "group_label": self.group_label,
            "icon": self.icon,
            "description": self.description,
            "detailed_description": self.detailed_description,
            "default_variant": self.default_variant,
            "default_variants": self.default_variants,
            "create_allow_context_change": self.create_allow_context_change,
            "create_allow_thumbnail": self.create_allow_thumbnail,
            "show_order": self.show_order,
            "pre_create_attributes_defs": pre_create_attributes_defs,
        }

    @classmethod
    def from_data(cls, data: Dict[str, Any]) -> "CreatorItem":
        pre_create_attributes_defs = data["pre_create_attributes_defs"]
        if pre_create_attributes_defs is not None:
            data["pre_create_attributes_defs"] = deserialize_attr_defs(
                pre_create_attributes_defs
            )

        data["creator_type"] = CreatorTypes.from_str(data["creator_type"])
        return cls(**data)


class CreateModel:
    def __init__(self, controller: AbstractPublisherBackend):
        self._log = None
        self._controller: AbstractPublisherBackend = controller

        self._create_context = CreateContext(
            controller.get_host(),
            headless=controller.is_headless(),
            reset=False
        )
        # State flags to prevent executing method which is already in progress
        self._creator_items = None

    @property
    def log(self) -> logging.Logger:
        if self._log is None:
            self._log = logging.getLogger(self.__class__.__name__)
        return self._log

    def is_host_valid(self) -> bool:
        return self._create_context.host_is_valid

    def get_create_context(self) -> CreateContext:
        return self._create_context

    def get_current_project_name(self) -> Union[str, None]:
        """Current project context defined by host.

        Returns:
            str: Project name.

        """
        return self._create_context.get_current_project_name()

    def get_current_folder_path(self) -> Union[str, None]:
        """Current context folder path defined by host.

        Returns:
            Union[str, None]: Folder path or None if folder is not set.
        """

        return self._create_context.get_current_folder_path()

    def get_current_task_name(self) -> Union[str, None]:
        """Current context task name defined by host.

        Returns:
            Union[str, None]: Task name or None if task is not set.
        """

        return self._create_context.get_current_task_name()

    def host_context_has_changed(self) -> bool:
        return self._create_context.context_has_changed

    def reset(self):
        self._create_context.reset_preparation()

        # Reset current context
        self._create_context.reset_current_context()

        self._create_context.reset_plugins()
        # Reset creator items
        self._creator_items = None

        self._reset_instances()
        self._create_context.reset_finalization()

    def get_creator_items(self) -> Dict[str, CreatorItem]:
        """Creators that can be shown in create dialog."""
        if self._creator_items is None:
            self._creator_items = self._collect_creator_items()
        return self._creator_items

    def get_creator_item_by_id(
        self, identifier: str
    ) -> Union[CreatorItem, None]:
        items = self.get_creator_items()
        return items.get(identifier)

    def get_creator_icon(
        self, identifier: str
    ) -> Union[str, Dict[str, Any], None]:
        """Function to receive icon for creator identifier.

        Args:
            identifier (str): Creator's identifier for which should
                be icon returned.

        """
        creator_item = self.get_creator_item_by_id(identifier)
        if creator_item is not None:
            return creator_item.icon
        return None

    def get_instances(self) -> List[CreatedInstance]:
        """Current instances in create context."""
        return list(self._create_context.instances_by_id.values())

    def get_instance_by_id(
        self, instance_id: str
    ) -> Union[CreatedInstance, None]:
        return self._create_context.instances_by_id.get(instance_id)

    def get_instances_by_id(
        self, instance_ids: Optional[Iterable[str]] = None
    ) -> Dict[str, Union[CreatedInstance, None]]:
        if instance_ids is None:
            instance_ids = self._create_context.instances_by_id.keys()
        return {
            instance_id: self.get_instance_by_id(instance_id)
            for instance_id in instance_ids
        }

    def get_convertor_items(self) -> Dict[str, ConvertorItem]:
        return self._create_context.convertor_items_by_id

    def get_product_name(
        self,
        creator_identifier: str,
        variant: str,
        task_name: Union[str, None],
        folder_path: Union[str, None],
        instance_id: Optional[str] = None
    ) -> str:
        """Get product name based on passed data.

        Args:
            creator_identifier (str): Identifier of creator which should be
                responsible for product name creation.
            variant (str): Variant value from user's input.
            task_name (str): Name of task for which is instance created.
            folder_path (str): Folder path for which is instance created.
            instance_id (Union[str, None]): Existing instance id when product
                name is updated.
        """

        creator = self._creators[creator_identifier]

        instance = None
        if instance_id:
            instance = self.get_instance_by_id(instance_id)

        project_name = self._controller.get_current_project_name()
        folder_item = self._controller.get_folder_item_by_path(
            project_name, folder_path
        )
        folder_entity = None
        task_item = None
        task_entity = None
        if folder_item is not None:
            folder_entity = self._controller.get_folder_entity(
                project_name, folder_item.entity_id
            )
            task_item = self._controller.get_task_item_by_name(
                project_name,
                folder_item.entity_id,
                task_name,
                CREATE_EVENT_SOURCE
            )

        if task_item is not None:
            task_entity = self._controller.get_task_entity(
                project_name, task_item.task_id
            )

        project_entity = self._controller.get_project_entity(project_name)
        args = (
            project_name,
            folder_entity,
            task_entity,
            variant
        )
        kwargs = {
            "instance": instance,
            "project_entity": project_entity,
        }
        # Backwards compatibility for 'project_entity' argument
        # - 'get_product_name' signature changed 24/07/08
        if not is_func_signature_supported(
            creator.get_product_name, *args, **kwargs
        ):
            kwargs.pop("project_entity")
        return creator.get_product_name(*args, **kwargs)

    def create(
        self,
        creator_identifier: str,
        product_name: str,
        instance_data: Dict[str, Any],
        options: Dict[str, Any],
    ):
        """Trigger creation and refresh of instances in UI."""

        success = True
        try:
            self._create_context.create_with_unified_error(
                creator_identifier, product_name, instance_data, options
            )

        except CreatorsOperationFailed as exc:
            success = False
            self._emit_event(
                "instances.create.failed",
                {
                    "title": "Creation failed",
                    "failed_info": exc.failed_info
                }
            )

        self._on_create_instance_change()
        return success

    def trigger_convertor_items(self, convertor_identifiers: List[str]):
        """Trigger legacy item convertors.

        This functionality requires to save and reset CreateContext. The reset
        is needed so Creators can collect converted items.

        Args:
            convertor_identifiers (list[str]): Identifiers of convertor
                plugins.
        """

        success = True
        try:
            self._create_context.run_convertors(convertor_identifiers)

        except ConvertorsOperationFailed as exc:
            success = False
            self._emit_event(
                "convertors.convert.failed",
                {
                    "title": "Conversion failed",
                    "failed_info": exc.failed_info
                }
            )

        if success:
            self._controller.emit_card_message(
                "Conversion finished"
            )
        else:
            self._controller.emit_card_message(
                "Conversion failed",
                CardMessageTypes.error
            )

    def save_changes(self, show_message: Optional[bool] = True) -> bool:
        """Save changes happened during creation.

        Trigger save of changes using host api. This functionality does not
        validate anything. It is required to do checks before this method is
        called to be able to give user actionable response e.g. check of
        context using 'host_context_has_changed'.

        Args:
            show_message (bool): Show message that changes were
                saved successfully.

        Returns:
            bool: Save of changes was successful.
        """

        if not self._create_context.host_is_valid:
            # TODO remove
            # Fake success save when host is not valid for CreateContext
            #   this is for testing as experimental feature
            return True

        try:
            self._create_context.save_changes()
            if show_message:
                self._controller.emit_card_message("Saved changes..")
            return True

        except CreatorsOperationFailed as exc:
            self._emit_event(
                "instances.save.failed",
                {
                    "title": "Instances save failed",
                    "failed_info": exc.failed_info
                }
            )

        return False

    def remove_instances(self, instance_ids: List[str]):
        """Remove instances based on instance ids.

        Args:
            instance_ids (List[str]): List of instance ids to remove.
        """

        # QUESTION Expect that instances are really removed? In that case reset
        #    is not required.
        self._remove_instances_from_context(instance_ids)

        self._on_create_instance_change()

    def get_creator_attribute_definitions(
        self, instances: List[CreatedInstance]
    ) -> List[Tuple[AbstractAttrDef, List[CreatedInstance], List[Any]]]:
        """Collect creator attribute definitions for multuple instances.

        Args:
            instances (List[CreatedInstance]): List of created instances for
                which should be attribute definitions returned.
        """

        # NOTE it would be great if attrdefs would have hash method implemented
        #   so they could be used as keys in dictionary
        output = []
        _attr_defs = {}
        for instance in instances:
            for attr_def in instance.creator_attribute_defs:
                found_idx = None
                for idx, _attr_def in _attr_defs.items():
                    if attr_def == _attr_def:
                        found_idx = idx
                        break

                value = None
                if attr_def.is_value_def:
                    value = instance.creator_attributes[attr_def.key]
                if found_idx is None:
                    idx = len(output)
                    output.append((attr_def, [instance], [value]))
                    _attr_defs[idx] = attr_def
                else:
                    item = output[found_idx]
                    item[1].append(instance)
                    item[2].append(value)
        return output

    def get_publish_attribute_definitions(
        self,
        instances: List[CreatedInstance],
        include_context: bool
    ) -> List[Tuple[
        str,
        List[AbstractAttrDef],
        Dict[str, List[Tuple[CreatedInstance, Any]]]
    ]]:
        """Collect publish attribute definitions for passed instances.

        Args:
            instances (list[CreatedInstance]): List of created instances for
                which should be attribute definitions returned.
            include_context (bool): Add context specific attribute definitions.

        """
        _tmp_items = []
        if include_context:
            _tmp_items.append(self._create_context)

        for instance in instances:
            _tmp_items.append(instance)

        all_defs_by_plugin_name = {}
        all_plugin_values = {}
        for item in _tmp_items:
            for plugin_name, attr_val in item.publish_attributes.items():
                attr_defs = attr_val.attr_defs
                if not attr_defs:
                    continue

                if plugin_name not in all_defs_by_plugin_name:
                    all_defs_by_plugin_name[plugin_name] = attr_val.attr_defs

                plugin_values = all_plugin_values.setdefault(plugin_name, {})

                for attr_def in attr_defs:
                    if isinstance(attr_def, UIDef):
                        continue

                    attr_values = plugin_values.setdefault(attr_def.key, [])

                    value = attr_val[attr_def.key]
                    attr_values.append((item, value))

        output = []
        for plugin in self._create_context.plugins_with_defs:
            plugin_name = plugin.__name__
            if plugin_name not in all_defs_by_plugin_name:
                continue
            output.append((
                plugin_name,
                all_defs_by_plugin_name[plugin_name],
                all_plugin_values
            ))
        return output

    def get_thumbnail_paths_for_instances(
        self, instance_ids: List[str]
    ) -> Dict[str, Union[str, None]]:
        thumbnail_paths_by_instance_id = (
            self._create_context.thumbnail_paths_by_instance_id
        )
        return {
            instance_id: thumbnail_paths_by_instance_id.get(instance_id)
            for instance_id in instance_ids
        }

    def set_thumbnail_paths_for_instances(
        self, thumbnail_path_mapping: Dict[str, str]
    ):
        thumbnail_paths_by_instance_id = (
            self._create_context.thumbnail_paths_by_instance_id
        )
        for instance_id, thumbnail_path in thumbnail_path_mapping.items():
            thumbnail_paths_by_instance_id[instance_id] = thumbnail_path

        self._emit_event(
            "instance.thumbnail.changed",
            {
                "mapping": thumbnail_path_mapping
            }
        )

    def _emit_event(self, topic: str, data: Optional[Dict[str, Any]] = None):
        self._controller.emit_event(topic, data)

    def _get_current_project_settings(self) -> Dict[str, Any]:
        """Current project settings.

        Returns:
            dict
        """

        return self._create_context.get_current_project_settings()

    @property
    def _creators(self) -> Dict[str, BaseCreator]:
        """All creators loaded in create context."""

        return self._create_context.creators

    def _reset_instances(self):
        """Reset create instances."""

        self._create_context.reset_context_data()
        with self._create_context.bulk_instances_collection():
            try:
                self._create_context.reset_instances()
            except CreatorsOperationFailed as exc:
                self._emit_event(
                    "instances.collection.failed",
                    {
                        "title": "Instance collection failed",
                        "failed_info": exc.failed_info
                    }
                )

            try:
                self._create_context.find_convertor_items()
            except ConvertorsOperationFailed as exc:
                self._emit_event(
                    "convertors.find.failed",
                    {
                        "title": "Collection of unsupported product failed",
                        "failed_info": exc.failed_info
                    }
                )

            try:
                self._create_context.execute_autocreators()

            except CreatorsOperationFailed as exc:
                self._emit_event(
                    "instances.create.failed",
                    {
                        "title": "AutoCreation failed",
                        "failed_info": exc.failed_info
                    }
                )

        self._on_create_instance_change()

    def _remove_instances_from_context(self, instance_ids: List[str]):
        instances_by_id = self._create_context.instances_by_id
        instances = [
            instances_by_id[instance_id]
            for instance_id in instance_ids
        ]
        try:
            self._create_context.remove_instances(instances)
        except CreatorsOperationFailed as exc:
            self._emit_event(
                "instances.remove.failed",
                {
                    "title": "Instance removement failed",
                    "failed_info": exc.failed_info
                }
            )

    def _on_create_instance_change(self):
        self._emit_event("instances.refresh.finished")

    def _collect_creator_items(self) -> Dict[str, CreatorItem]:
        # TODO add crashed initialization of create plugins to report
        output = {}
        allowed_creator_pattern = self._get_allowed_creators_pattern()
        for identifier, creator in self._create_context.creators.items():
            try:
                if self._is_label_allowed(
                    creator.label, allowed_creator_pattern
                ):
                    output[identifier] = CreatorItem.from_creator(creator)
                    continue
                self.log.debug(f"{creator.label} not allowed for context")
            except Exception:
                self.log.error(
                    "Failed to create creator item for '%s'",
                    identifier,
                    exc_info=True
                )

        return output

    def _get_allowed_creators_pattern(self) -> Union[Pattern, None]:
        """Provide regex pattern for configured creator labels in this context

        If no profile matches current context, it shows all creators.
        Support usage of regular expressions for configured values.
        Returns:
            (re.Pattern)[optional]: None or regex compiled patterns
                into single one ('Render|Image.*')
        """

        task_type = self._create_context.get_current_task_type()
        project_settings = self._get_current_project_settings()

        filter_creator_profiles = (
            project_settings
            ["core"]
            ["tools"]
            ["creator"]
            ["filter_creator_profiles"]
        )
        filtering_criteria = {
            "task_names": self.get_current_task_name(),
            "task_types": task_type,
            "host_names": self._create_context.host_name
        }
        profile = filter_profiles(
            filter_creator_profiles,
            filtering_criteria,
            logger=self.log
        )

        allowed_creator_pattern = None
        if profile:
            allowed_creator_labels = {
                label
                for label in profile["creator_labels"]
                if label
            }
            self.log.debug(f"Only allowed `{allowed_creator_labels}` creators")
            allowed_creator_pattern = (
                re.compile("|".join(allowed_creator_labels)))
        return allowed_creator_pattern

    def _is_label_allowed(
        self,
        label: str,
        allowed_labels_regex: Union[Pattern, None]
    ) -> bool:
        """Implement regex support for allowed labels.

        Args:
            label (str): Label of creator - shown in Publisher
            allowed_labels_regex (re.Pattern): compiled regular expression
        """
        if not allowed_labels_regex:
            return True
        return bool(allowed_labels_regex.match(label))
