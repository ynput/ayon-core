import logging
import re
from typing import (
    Union,
    List,
    Dict,
    Tuple,
    Any,
    Optional,
    Iterable,
    Pattern,
)

from ayon_core.lib.attribute_definitions import (
    serialize_attr_defs,
    deserialize_attr_defs,
    AbstractAttrDef,
    EnumDef,
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
    AttributeValues,
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
_DEFAULT_VALUE = object()


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


class InstanceItem:
    def __init__(
        self,
        instance_id: str,
        creator_identifier: str,
        label: str,
        group_label: str,
        product_type: str,
        product_name: str,
        variant: str,
        folder_path: Optional[str],
        task_name: Optional[str],
        is_active: bool,
        has_promised_context: bool,
    ):
        self._instance_id: str = instance_id
        self._creator_identifier: str = creator_identifier
        self._label: str = label
        self._group_label: str = group_label
        self._product_type: str = product_type
        self._product_name: str = product_name
        self._variant: str = variant
        self._folder_path: Optional[str] = folder_path
        self._task_name: Optional[str] = task_name
        self._is_active: bool = is_active
        self._has_promised_context: bool = has_promised_context

    @property
    def id(self):
        return self._instance_id

    @property
    def creator_identifier(self):
        return self._creator_identifier

    @property
    def label(self):
        return self._label

    @property
    def group_label(self):
        return self._group_label

    @property
    def product_type(self):
        return self._product_type

    @property
    def has_promised_context(self):
        return self._has_promised_context

    def get_variant(self):
        return self._variant

    def set_variant(self, variant):
        self._variant = variant

    def get_product_name(self):
        return self._product_name

    def set_product_name(self, product_name):
        self._product_name = product_name

    def get_folder_path(self):
        return self._folder_path

    def set_folder_path(self, folder_path):
        self._folder_path = folder_path

    def get_task_name(self):
        return self._task_name

    def set_task_name(self, task_name):
        self._task_name = task_name

    def get_is_active(self):
        return self._is_active

    def set_is_active(self, is_active):
        self._is_active = is_active

    product_name = property(get_product_name, set_product_name)
    variant = property(get_variant, set_variant)
    folder_path = property(get_folder_path, set_folder_path)
    task_name = property(get_task_name, set_task_name)
    is_active = property(get_is_active, set_is_active)

    @classmethod
    def from_instance(cls, instance: CreatedInstance):
        return InstanceItem(
            instance.id,
            instance.creator_identifier,
            instance.label or "N/A",
            instance.group_label,
            instance.product_type,
            instance.product_name,
            instance["variant"],
            instance["folderPath"],
            instance["task"],
            instance["active"],
            instance.has_promised_context,
        )


def _merge_attr_defs(
    attr_def_src: AbstractAttrDef, attr_def_new: AbstractAttrDef
) -> Optional[AbstractAttrDef]:
    if not attr_def_src.enabled and attr_def_new.enabled:
        attr_def_src.enabled = True
    if not attr_def_src.visible and attr_def_new.visible:
        attr_def_src.visible = True

    if not isinstance(attr_def_src, EnumDef):
        return None
    if attr_def_src.items == attr_def_new.items:
        return None

    src_item_values = {
        item["value"]
        for item in attr_def_src.items
    }
    for item in attr_def_new.items:
        if item["value"] not in src_item_values:
            attr_def_src.items.append(item)


def merge_attr_defs(attr_defs: List[List[AbstractAttrDef]]):
    if not attr_defs:
        return []
    if len(attr_defs) == 1:
        return attr_defs[0]

    # Pop first and create clone of attribute definitions
    defs_union: List[AbstractAttrDef] = [
        attr_def.clone()
        for attr_def in attr_defs.pop(0)
    ]
    for instance_attr_defs in attr_defs:
        idx = 0
        for attr_idx, attr_def in enumerate(instance_attr_defs):
            # QUESTION should we merge NumberDef too? Use lowest min and
            #   biggest max...
            is_enum = isinstance(attr_def, EnumDef)
            match_idx = None
            match_attr = None
            for union_idx, union_def in enumerate(defs_union):
                if is_enum and (
                    not isinstance(union_def, EnumDef)
                    or union_def.multiselection != attr_def.multiselection
                ):
                    continue

                if (
                    attr_def.compare_to_def(
                        union_def,
                        ignore_default=True,
                        ignore_enabled=True,
                        ignore_visible=True,
                        ignore_def_type_compare=is_enum
                    )
                ):
                    match_idx = union_idx
                    match_attr = union_def
                    break

            if match_attr is not None:
                new_attr_def = _merge_attr_defs(match_attr, attr_def)
                if new_attr_def is not None:
                    defs_union[match_idx] = new_attr_def
                idx = match_idx + 1
                continue

            defs_union.insert(idx, attr_def.clone())
            idx += 1
    return defs_union


class CreateModel:
    _CONTEXT_KEYS = {
        "active",
        "folderPath",
        "task",
        "variant",
        "productName",
    }

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

        self._emit_event("create.model.reset")

        self._create_context.add_instances_added_callback(
            self._cc_added_instance
        )
        self._create_context.add_instances_removed_callback (
            self._cc_removed_instance
        )
        self._create_context.add_value_changed_callback(
            self._cc_value_changed
        )
        self._create_context.add_pre_create_attr_defs_change_callback (
            self._cc_pre_create_attr_changed
        )
        self._create_context.add_create_attr_defs_change_callback (
            self._cc_create_attr_changed
        )
        self._create_context.add_publish_attr_defs_change_callback (
            self._cc_publish_attr_changed
        )

        self._create_context.reset_finalization()

    def get_creator_items(self) -> Dict[str, CreatorItem]:
        """Creators that can be shown in create dialog."""
        if self._creator_items is None:
            self._refresh_creator_items()
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

    def get_instance_items(self) -> List[InstanceItem]:
        """Current instances in create context."""
        return [
            InstanceItem.from_instance(instance)
            for instance in self._create_context.instances_by_id.values()
        ]

    def get_instance_item_by_id(
        self, instance_id: str
    ) -> Union[InstanceItem, None]:
        instance = self._create_context.instances_by_id.get(instance_id)
        if instance is None:
            return None

        return InstanceItem.from_instance(instance)

    def get_instance_items_by_id(
        self, instance_ids: Optional[Iterable[str]] = None
    ) -> Dict[str, Union[InstanceItem, None]]:
        if instance_ids is None:
            instance_ids = self._create_context.instances_by_id.keys()
        return {
            instance_id: self.get_instance_item_by_id(instance_id)
            for instance_id in instance_ids
        }

    def get_instances_context_info(
        self, instance_ids: Optional[Iterable[str]] = None
    ):
        instances = self._get_instances_by_id(instance_ids).values()
        return self._create_context.get_instances_context_info(
            instances
        )

    def set_instances_context_info(self, changes_by_instance_id):
        with self._create_context.bulk_value_changes(CREATE_EVENT_SOURCE):
            for instance_id, changes in changes_by_instance_id.items():
                instance = self._get_instance_by_id(instance_id)
                for key, value in changes.items():
                    instance[key] = value
        self._emit_event(
            "create.model.instances.context.changed",
            {
                "instance_ids": list(changes_by_instance_id.keys())
            }
        )

    def set_instances_active_state(
        self, active_state_by_id: Dict[str, bool]
    ):
        with self._create_context.bulk_value_changes(CREATE_EVENT_SOURCE):
            for instance_id, active in active_state_by_id.items():
                instance = self._create_context.get_instance_by_id(instance_id)
                instance["active"] = active

        self._emit_event(
            "create.model.instances.context.changed",
            {
                "instance_ids": set(active_state_by_id.keys())
            }
        )

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
            instance = self._get_instance_by_id(instance_id)

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
            with self._create_context.bulk_add_instances():
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

    def set_instances_create_attr_values(self, instance_ids, key, value):
        self._set_instances_create_attr_values(instance_ids, key, value)

    def revert_instances_create_attr_values(self, instance_ids, key):
        self._set_instances_create_attr_values(
            instance_ids, key, _DEFAULT_VALUE
        )

    def get_creator_attribute_definitions(
        self, instance_ids: List[str]
    ) -> List[Tuple[AbstractAttrDef, Dict[str, Dict[str, Any]]]]:
        """Collect creator attribute definitions for multuple instances.

        Args:
            instance_ids (List[str]): List of created instances for
                which should be attribute definitions returned.

        """
        # NOTE it would be great if attrdefs would have hash method implemented
        #   so they could be used as keys in dictionary
        output = []
        _attr_defs = {}
        for instance_id in instance_ids:
            instance = self._get_instance_by_id(instance_id)
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
                    output.append((
                        attr_def,
                        {
                            instance_id: {
                                "value": value,
                                "default": attr_def.default
                            }
                        }
                    ))
                    _attr_defs[idx] = attr_def
                else:
                    _, info_by_id = output[found_idx]
                    info_by_id[instance_id] = {
                        "value": value,
                        "default": attr_def.default
                    }

        return output

    def set_instances_publish_attr_values(
        self, instance_ids, plugin_name, key, value
    ):
        self._set_instances_publish_attr_values(
            instance_ids, plugin_name, key, value
        )

    def revert_instances_publish_attr_values(
        self, instance_ids, plugin_name, key
    ):
        self._set_instances_publish_attr_values(
            instance_ids, plugin_name, key, _DEFAULT_VALUE
        )

    def get_publish_attribute_definitions(
        self,
        instance_ids: List[str],
        include_context: bool
    ) -> List[Tuple[
        str,
        List[AbstractAttrDef],
        Dict[str, List[Tuple[str, Any, Any]]]
    ]]:
        """Collect publish attribute definitions for passed instances.

        Args:
            instance_ids (List[str]): List of created instances for
                which should be attribute definitions returned.
            include_context (bool): Add context specific attribute definitions.

        """
        _tmp_items = []
        if include_context:
            _tmp_items.append(self._create_context)

        for instance_id in instance_ids:
            _tmp_items.append(self._get_instance_by_id(instance_id))

        all_defs_by_plugin_name = {}
        all_plugin_values = {}
        for item in _tmp_items:
            item_id = None
            if isinstance(item, CreatedInstance):
                item_id = item.id

            for plugin_name, attr_val in item.publish_attributes.items():
                if not isinstance(attr_val, AttributeValues):
                    continue
                attr_defs = attr_val.attr_defs
                if not attr_defs:
                    continue

                plugin_attr_defs = all_defs_by_plugin_name.setdefault(
                    plugin_name, []
                )
                plugin_values = all_plugin_values.setdefault(plugin_name, {})

                plugin_attr_defs.append(attr_defs)

                for attr_def in attr_defs:
                    if isinstance(attr_def, UIDef):
                        continue
                    attr_values = plugin_values.setdefault(attr_def.key, [])
                    attr_values.append(
                        (item_id, attr_val[attr_def.key], attr_def.default)
                    )

        attr_defs_by_plugin_name = {}
        for plugin_name, attr_defs in all_defs_by_plugin_name.items():
            attr_defs_by_plugin_name[plugin_name] = merge_attr_defs(attr_defs)

        output = []
        for plugin in self._create_context.plugins_with_defs:
            plugin_name = plugin.__name__
            if plugin_name not in all_defs_by_plugin_name:
                continue
            output.append((
                plugin_name,
                attr_defs_by_plugin_name[plugin_name],
                all_plugin_values[plugin_name],
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

    def _emit_event(
        self,
        topic: str,
        data: Optional[Dict[str, Any]] = None
    ):
        self._controller.emit_event(topic, data, CREATE_EVENT_SOURCE)

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

    def _get_instance_by_id(
        self, instance_id: str
    ) -> Union[CreatedInstance, None]:
        return self._create_context.instances_by_id.get(instance_id)

    def _get_instances_by_id(
        self, instance_ids: Optional[Iterable[str]]
    ) -> Dict[str, Union[CreatedInstance, None]]:
        if instance_ids is None:
            instance_ids = self._create_context.instances_by_id.keys()
        return {
            instance_id: self._get_instance_by_id(instance_id)
            for instance_id in instance_ids
        }

    def _reset_instances(self):
        """Reset create instances."""

        self._create_context.reset_context_data()
        with self._create_context.bulk_add_instances():
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

    def _refresh_creator_items(self, identifiers=None):
        if identifiers is None:
            self._creator_items = self._collect_creator_items()
            return

        for identifier in identifiers:
            if identifier not in self._creator_items:
                continue
            creator = self._create_context.creators.get(identifier)
            if creator is None:
                continue
            self._creator_items[identifier] = (
                CreatorItem.from_creator(creator)
            )

    def _set_instances_create_attr_values(self, instance_ids, key, value):
        with self._create_context.bulk_value_changes(CREATE_EVENT_SOURCE):
            for instance_id in instance_ids:
                instance = self._get_instance_by_id(instance_id)
                creator_attributes = instance["creator_attributes"]
                attr_def = creator_attributes.get_attr_def(key)
                if (
                    attr_def is None
                    or not attr_def.is_value_def
                    or not attr_def.visible
                    or not attr_def.enabled
                ):
                    continue

                if value is _DEFAULT_VALUE:
                    creator_attributes[key] = attr_def.default

                elif attr_def.is_value_valid(value):
                    creator_attributes[key] = value

    def _set_instances_publish_attr_values(
        self, instance_ids, plugin_name, key, value
    ):
        with self._create_context.bulk_value_changes(CREATE_EVENT_SOURCE):
            for instance_id in instance_ids:
                if instance_id is None:
                    instance = self._create_context
                else:
                    instance = self._get_instance_by_id(instance_id)
                plugin_val = instance.publish_attributes[plugin_name]
                attr_def = plugin_val.get_attr_def(key)
                # Ignore if attribute is not available or enabled/visible
                #   on the instance, or the value is not valid for definition
                if (
                    attr_def is None
                    or not attr_def.is_value_def
                    or not attr_def.visible
                    or not attr_def.enabled
                ):
                    continue

                if value is _DEFAULT_VALUE:
                    plugin_val[key] = attr_def.default

                elif attr_def.is_value_valid(value):
                    plugin_val[key] = value

    def _cc_added_instance(self, event):
        instance_ids = {
            instance.id
            for instance in event.data["instances"]
        }
        self._emit_event(
            "create.context.added.instance",
            {"instance_ids": instance_ids},
        )

    def _cc_removed_instance(self, event):
        instance_ids = {
            instance.id
            for instance in event.data["instances"]
        }
        self._emit_event(
            "create.context.removed.instance",
            {"instance_ids": instance_ids},
        )

    def _cc_value_changed(self, event):
        if event.source == CREATE_EVENT_SOURCE:
            return

        instance_changes = {}
        context_changed_ids = set()
        for item in event.data["changes"]:
            instance_id = None
            if item["instance"]:
                instance_id = item["instance"].id
            changes = item["changes"]
            instance_changes[instance_id] = changes
            if instance_id is None:
                continue

            if self._CONTEXT_KEYS.intersection(set(changes)):
                context_changed_ids.add(instance_id)

        self._emit_event(
            "create.context.value.changed",
            {"instance_changes": instance_changes},
        )
        if context_changed_ids:
            self._emit_event(
                "create.model.instances.context.changed",
                {"instance_ids": list(context_changed_ids)},
            )

    def _cc_pre_create_attr_changed(self, event):
        identifiers = event["identifiers"]
        self._refresh_creator_items(identifiers)
        self._emit_event(
            "create.context.pre.create.attrs.changed",
            {"identifiers": identifiers},
        )

    def _cc_create_attr_changed(self, event):
        instance_ids = {
            instance.id
            for instance in event.data["instances"]
        }
        self._emit_event(
            "create.context.create.attrs.changed",
            {"instance_ids": instance_ids},
        )

    def _cc_publish_attr_changed(self, event):
        instance_changes = event.data["instance_changes"]
        event_data = {
            instance_id: instance_data["plugin_names"]
            for instance_id, instance_data in instance_changes.items()
        }
        self._emit_event(
            "create.context.publish.attrs.changed",
            event_data,
        )

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
