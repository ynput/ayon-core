import copy
import collections
from uuid import uuid4

from ayon_core.lib.attribute_definitions import (
    UnknownDef,
    serialize_attr_defs,
    deserialize_attr_defs,
)
from ayon_core.pipeline import (
    AYON_INSTANCE_ID,
    AVALON_INSTANCE_ID,
)

from .exceptions import ImmutableKeyError
from .changes import TrackChangesItem


class ConvertorItem:
    """Item representing convertor plugin.

    Args:
        identifier (str): Identifier of convertor.
        label (str): Label which will be shown in UI.
    """

    def __init__(self, identifier, label):
        self._id = str(uuid4())
        self.identifier = identifier
        self.label = label

    @property
    def id(self):
        return self._id

    def to_data(self):
        return {
            "id": self.id,
            "identifier": self.identifier,
            "label": self.label
        }

    @classmethod
    def from_data(cls, data):
        obj = cls(data["identifier"], data["label"])
        obj._id = data["id"]
        return obj


class InstanceMember:
    """Representation of instance member.

    TODO:
    Implement and use!
    """

    def __init__(self, instance, name):
        self.instance = instance

        instance.add_members(self)

        self.name = name
        self._actions = []

    def add_action(self, label, callback):
        self._actions.append({
            "label": label,
            "callback": callback
        })


class AttributeValues:
    """Container which keep values of Attribute definitions.

    Goal is to have one object which hold values of attribute definitions for
    single instance.

    Has dictionary like methods. Not all of them are allowed all the time.

    Args:
        attr_defs(AbstractAttrDef): Definitions of value type and properties.
        values(dict): Values after possible conversion.
        origin_data(dict): Values loaded from host before conversion.
    """

    def __init__(self, attr_defs, values, origin_data=None):
        if origin_data is None:
            origin_data = copy.deepcopy(values)
        self._origin_data = origin_data

        attr_defs_by_key = {
            attr_def.key: attr_def
            for attr_def in attr_defs
            if attr_def.is_value_def
        }
        for key, value in values.items():
            if key not in attr_defs_by_key:
                new_def = UnknownDef(key, label=key, default=value)
                attr_defs.append(new_def)
                attr_defs_by_key[key] = new_def

        self._attr_defs = attr_defs
        self._attr_defs_by_key = attr_defs_by_key

        self._data = {}
        for attr_def in attr_defs:
            value = values.get(attr_def.key)
            if value is not None:
                self._data[attr_def.key] = value

    def __setitem__(self, key, value):
        if key not in self._attr_defs_by_key:
            raise KeyError("Key \"{}\" was not found.".format(key))

        self.update({key: value})

    def __getitem__(self, key):
        if key not in self._attr_defs_by_key:
            return self._data[key]
        return self._data.get(key, self._attr_defs_by_key[key].default)

    def __contains__(self, key):
        return key in self._attr_defs_by_key

    def get(self, key, default=None):
        if key in self._attr_defs_by_key:
            return self[key]
        return default

    def keys(self):
        return self._attr_defs_by_key.keys()

    def values(self):
        for key in self._attr_defs_by_key.keys():
            yield self._data.get(key)

    def items(self):
        for key in self._attr_defs_by_key.keys():
            yield key, self._data.get(key)

    def update(self, value):
        changes = {}
        for _key, _value in dict(value).items():
            if _key in self._data and self._data.get(_key) == _value:
                continue
            self._data[_key] = _value
            changes[_key] = _value

    def pop(self, key, default=None):
        value = self._data.pop(key, default)
        # Remove attribute definition if is 'UnknownDef'
        # - gives option to get rid of unknown values
        attr_def = self._attr_defs_by_key.get(key)
        if isinstance(attr_def, UnknownDef):
            self._attr_defs_by_key.pop(key)
            self._attr_defs.remove(attr_def)
        return value

    def reset_values(self):
        self._data = {}

    def mark_as_stored(self):
        self._origin_data = copy.deepcopy(self._data)

    @property
    def attr_defs(self):
        """Pointer to attribute definitions.

        Returns:
            List[AbstractAttrDef]: Attribute definitions.
        """

        return list(self._attr_defs)

    @property
    def origin_data(self):
        return copy.deepcopy(self._origin_data)

    def data_to_store(self):
        """Create new dictionary with data to store.

        Returns:
            Dict[str, Any]: Attribute values that should be stored.
        """

        output = {}
        for key in self._data:
            output[key] = self[key]

        for key, attr_def in self._attr_defs_by_key.items():
            if key not in output:
                output[key] = attr_def.default
        return output

    def get_serialized_attr_defs(self):
        """Serialize attribute definitions to json serializable types.

        Returns:
            List[Dict[str, Any]]: Serialized attribute definitions.
        """

        return serialize_attr_defs(self._attr_defs)


class CreatorAttributeValues(AttributeValues):
    """Creator specific attribute values of an instance.

    Args:
        instance (CreatedInstance): Instance for which are values hold.
    """

    def __init__(self, instance, *args, **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)


class PublishAttributeValues(AttributeValues):
    """Publish plugin specific attribute values.

    Values are for single plugin which can be on `CreatedInstance`
    or context values stored on `CreateContext`.

    Args:
        publish_attributes(PublishAttributes): Wrapper for multiple publish
            attributes is used as parent object.
    """

    def __init__(self, publish_attributes, *args, **kwargs):
        self.publish_attributes = publish_attributes
        super().__init__(*args, **kwargs)

    @property
    def parent(self):
        return self.publish_attributes.parent


class PublishAttributes:
    """Wrapper for publish plugin attribute definitions.

    Cares about handling attribute definitions of multiple publish plugins.
    Keep information about attribute definitions and their values.

    Args:
        parent(CreatedInstance, CreateContext): Parent for which will be
            data stored and from which are data loaded.
        origin_data(dict): Loaded data by plugin class name.
        attr_plugins(Union[List[pyblish.api.Plugin], None]): List of publish
            plugins that may have defined attribute definitions.
    """

    def __init__(self, parent, origin_data, attr_plugins=None):
        self.parent = parent
        self._origin_data = copy.deepcopy(origin_data)

        attr_plugins = attr_plugins or []
        self.attr_plugins = attr_plugins

        self._data = copy.deepcopy(origin_data)
        self._plugin_names_order = []
        self._missing_plugins = []

        self.set_publish_plugins(attr_plugins)

    def __getitem__(self, key):
        return self._data[key]

    def __contains__(self, key):
        return key in self._data

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()

    def pop(self, key, default=None):
        """Remove or reset value for plugin.

        Plugin values are reset to defaults if plugin is available but
        data of plugin which was not found are removed.

        Args:
            key(str): Plugin name.
            default: Default value if plugin was not found.
        """

        if key not in self._data:
            return default

        if key in self._missing_plugins:
            self._missing_plugins.remove(key)
            removed_item = self._data.pop(key)
            return removed_item.data_to_store()

        value_item = self._data[key]
        # Prepare value to return
        output = value_item.data_to_store()
        # Reset values
        value_item.reset_values()
        return output

    def plugin_names_order(self):
        """Plugin names order by their 'order' attribute."""

        for name in self._plugin_names_order:
            yield name

    def mark_as_stored(self):
        self._origin_data = copy.deepcopy(self.data_to_store())

    def data_to_store(self):
        """Convert attribute values to "data to store"."""

        output = {}
        for key, attr_value in self._data.items():
            output[key] = attr_value.data_to_store()
        return output

    @property
    def origin_data(self):
        return copy.deepcopy(self._origin_data)

    def set_publish_plugins(self, attr_plugins):
        """Set publish plugins attribute definitions."""

        self._plugin_names_order = []
        self._missing_plugins = []
        self.attr_plugins = attr_plugins or []

        origin_data = self._origin_data
        data = self._data
        self._data = {}
        added_keys = set()
        for plugin in attr_plugins:
            output = plugin.convert_attribute_values(data)
            if output is not None:
                data = output
            attr_defs = plugin.get_attribute_defs()
            if not attr_defs:
                continue

            key = plugin.__name__
            added_keys.add(key)
            self._plugin_names_order.append(key)

            value = data.get(key) or {}
            orig_value = copy.deepcopy(origin_data.get(key) or {})
            self._data[key] = PublishAttributeValues(
                self, attr_defs, value, orig_value
            )

        for key, value in data.items():
            if key not in added_keys:
                self._missing_plugins.append(key)
                self._data[key] = PublishAttributeValues(
                    self, [], value, value
                )

    def serialize_attributes(self):
        return {
            "attr_defs": {
                plugin_name: attrs_value.get_serialized_attr_defs()
                for plugin_name, attrs_value in self._data.items()
            },
            "plugin_names_order": self._plugin_names_order,
            "missing_plugins": self._missing_plugins
        }

    def deserialize_attributes(self, data):
        self._plugin_names_order = data["plugin_names_order"]
        self._missing_plugins = data["missing_plugins"]

        attr_defs = deserialize_attr_defs(data["attr_defs"])

        origin_data = self._origin_data
        data = self._data
        self._data = {}

        added_keys = set()
        for plugin_name, attr_defs_data in attr_defs.items():
            attr_defs = deserialize_attr_defs(attr_defs_data)
            value = data.get(plugin_name) or {}
            orig_value = copy.deepcopy(origin_data.get(plugin_name) or {})
            self._data[plugin_name] = PublishAttributeValues(
                self, attr_defs, value, orig_value
            )

        for key, value in data.items():
            if key not in added_keys:
                self._missing_plugins.append(key)
                self._data[key] = PublishAttributeValues(
                    self, [], value, value
                )


class CreatedInstance:
    """Instance entity with data that will be stored to workfile.

    I think `data` must be required argument containing all minimum information
    about instance like "folderPath" and "task" and all data used for filling
    product name as creators may have custom data for product name filling.

    Notes:
        Object have 2 possible initialization. One using 'creator' object which
            is recommended for api usage. Second by passing information about
            creator.

    Args:
        product_type (str): Product type that will be created.
        product_name (str): Name of product that will be created.
        data (Dict[str, Any]): Data used for filling product name or override
            data from already existing instance.
        creator (Union[BaseCreator, None]): Creator responsible for instance.
        creator_identifier (str): Identifier of creator plugin.
        creator_label (str): Creator plugin label.
        group_label (str): Default group label from creator plugin.
        creator_attr_defs (List[AbstractAttrDef]): Attribute definitions from
            creator.
    """

    # Keys that can't be changed or removed from data after loading using
    #   creator.
    # - 'creator_attributes' and 'publish_attributes' can change values of
    #   their individual children but not on their own
    __immutable_keys = (
        "id",
        "instance_id",
        "product_type",
        "creator_identifier",
        "creator_attributes",
        "publish_attributes"
    )

    def __init__(
        self,
        product_type,
        product_name,
        data,
        creator=None,
        creator_identifier=None,
        creator_label=None,
        group_label=None,
        creator_attr_defs=None,
    ):
        if creator is not None:
            creator_identifier = creator.identifier
            group_label = creator.get_group_label()
            creator_label = creator.label
            creator_attr_defs = creator.get_instance_attr_defs()

        self._creator_label = creator_label
        self._group_label = group_label or creator_identifier

        # Instance members may have actions on them
        # TODO implement members logic
        self._members = []

        # Data that can be used for lifetime of object
        self._transient_data = {}

        # Create a copy of passed data to avoid changing them on the fly
        data = copy.deepcopy(data or {})

        # Pop dictionary values that will be converted to objects to be able
        #   catch changes
        orig_creator_attributes = data.pop("creator_attributes", None) or {}
        orig_publish_attributes = data.pop("publish_attributes", None) or {}

        # Store original value of passed data
        self._orig_data = copy.deepcopy(data)

        # Pop 'productType' and 'productName' to prevent unexpected changes
        data.pop("productType", None)
        data.pop("productName", None)
        # Backwards compatibility with OpenPype instances
        data.pop("family", None)
        data.pop("subset", None)

        asset_name = data.pop("asset", None)
        if "folderPath" not in data:
            data["folderPath"] = asset_name

        # QUESTION Does it make sense to have data stored as ordered dict?
        self._data = collections.OrderedDict()
        # QUESTION Do we need this "id" information on instance?
        item_id = data.get("id")
        # TODO use only 'AYON_INSTANCE_ID' when all hosts support it
        if item_id not in {AYON_INSTANCE_ID, AVALON_INSTANCE_ID}:
            item_id = AVALON_INSTANCE_ID
        self._data["id"] = item_id
        self._data["productType"] = product_type
        self._data["productName"] = product_name
        self._data["active"] = data.get("active", True)
        self._data["creator_identifier"] = creator_identifier

        # Pop from source data all keys that are defined in `_data` before
        #   this moment and through their values away
        # - they should be the same and if are not then should not change
        #   already set values
        for key in self._data.keys():
            if key in data:
                data.pop(key)

        self._data["variant"] = self._data.get("variant") or ""
        # Stored creator specific attribute values
        # {key: value}
        creator_values = copy.deepcopy(orig_creator_attributes)

        self._data["creator_attributes"] = CreatorAttributeValues(
            self,
            list(creator_attr_defs),
            creator_values,
            orig_creator_attributes
        )

        # Stored publish specific attribute values
        # {<plugin name>: {key: value}}
        # - must be set using 'set_publish_plugins'
        self._data["publish_attributes"] = PublishAttributes(
            self, orig_publish_attributes, None
        )
        if data:
            self._data.update(data)

        if not self._data.get("instance_id"):
            self._data["instance_id"] = str(uuid4())

        self._folder_is_valid = self.has_set_folder
        self._task_is_valid = self.has_set_task

    def __str__(self):
        return (
            "<CreatedInstance {product[name]}"
            " ({product[type]}[{creator_identifier}])> {data}"
        ).format(
            creator_identifier=self.creator_identifier,
            product={"name": self.product_name, "type": self.product_type},
            data=str(self._data)
        )

    # --- Dictionary like methods ---
    def __getitem__(self, key):
        return self._data[key]

    def __contains__(self, key):
        return key in self._data

    def __setitem__(self, key, value):
        # Validate immutable keys
        if key not in self.__immutable_keys:
            self._data[key] = value

        elif value != self._data.get(key):
            # Raise exception if key is immutable and value has changed
            raise ImmutableKeyError(key)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def pop(self, key, *args, **kwargs):
        # Raise exception if is trying to pop key which is immutable
        if key in self.__immutable_keys:
            raise ImmutableKeyError(key)

        self._data.pop(key, *args, **kwargs)

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()
    # ------

    @property
    def product_type(self):
        return self._data["productType"]

    @property
    def product_name(self):
        return self._data["productName"]

    @property
    def label(self):
        label = self._data.get("label")
        if not label:
            label = self.product_name
        return label

    @property
    def group_label(self):
        label = self._data.get("group")
        if label:
            return label
        return self._group_label

    @property
    def origin_data(self):
        output = copy.deepcopy(self._orig_data)
        output["creator_attributes"] = self.creator_attributes.origin_data
        output["publish_attributes"] = self.publish_attributes.origin_data
        return output

    @property
    def creator_identifier(self):
        return self._data["creator_identifier"]

    @property
    def creator_label(self):
        return self._creator_label or self.creator_identifier

    @property
    def id(self):
        """Instance identifier.

        Returns:
            str: UUID of instance.
        """

        return self._data["instance_id"]

    @property
    def data(self):
        """Legacy access to data.

        Access to data is needed to modify values.

        Returns:
            CreatedInstance: Object can be used as dictionary but with
                validations of immutable keys.
        """

        return self

    @property
    def transient_data(self):
        """Data stored for lifetime of instance object.

        These data are not stored to scene and will be lost on object
        deletion.

        Can be used to store objects. In some host implementations is not
        possible to reference to object in scene with some unique identifier
        (e.g. node in Fusion.). In that case it is handy to store the object
        here. Should be used that way only if instance data are stored on the
        node itself.

        Returns:
            Dict[str, Any]: Dictionary object where you can store data related
                to instance for lifetime of instance object.
        """

        return self._transient_data

    def changes(self):
        """Calculate and return changes."""

        return TrackChangesItem(self.origin_data, self.data_to_store())

    def mark_as_stored(self):
        """Should be called when instance data are stored.

        Origin data are replaced by current data so changes are cleared.
        """

        orig_keys = set(self._orig_data.keys())
        for key, value in self._data.items():
            orig_keys.discard(key)
            if key in ("creator_attributes", "publish_attributes"):
                continue
            self._orig_data[key] = copy.deepcopy(value)

        for key in orig_keys:
            self._orig_data.pop(key)

        self.creator_attributes.mark_as_stored()
        self.publish_attributes.mark_as_stored()

    @property
    def creator_attributes(self):
        return self._data["creator_attributes"]

    @property
    def creator_attribute_defs(self):
        """Attribute definitions defined by creator plugin.

        Returns:
              List[AbstractAttrDef]: Attribute definitions.
        """

        return self.creator_attributes.attr_defs

    @property
    def publish_attributes(self):
        return self._data["publish_attributes"]

    def data_to_store(self):
        """Collect data that contain json parsable types.

        It is possible to recreate the instance using these data.

        Todos:
            We probably don't need OrderedDict. When data are loaded they
                are not ordered anymore.

        Returns:
            OrderedDict: Ordered dictionary with instance data.
        """

        output = collections.OrderedDict()
        for key, value in self._data.items():
            if key in ("creator_attributes", "publish_attributes"):
                continue
            output[key] = value

        output["creator_attributes"] = self.creator_attributes.data_to_store()
        output["publish_attributes"] = self.publish_attributes.data_to_store()

        return output

    @classmethod
    def from_existing(cls, instance_data, creator):
        """Convert instance data from workfile to CreatedInstance.

        Args:
            instance_data (Dict[str, Any]): Data in a structure ready for
                'CreatedInstance' object.
            creator (BaseCreator): Creator plugin which is creating the
                instance of for which the instance belong.
        """

        instance_data = copy.deepcopy(instance_data)

        product_type = instance_data.get("productType")
        if product_type is None:
            product_type = instance_data.get("family")
            if product_type is None:
                product_type = creator.product_type
        product_name = instance_data.get("productName")
        if product_name is None:
            product_name = instance_data.get("subset")

        return cls(
            product_type, product_name, instance_data, creator
        )

    def set_publish_plugins(self, attr_plugins):
        """Set publish plugins with attribute definitions.

        This method should be called only from 'CreateContext'.

        Args:
            attr_plugins (List[pyblish.api.Plugin]): Pyblish plugins which
                inherit from 'AYONPyblishPluginMixin' and may contain
                attribute definitions.
        """

        self.publish_attributes.set_publish_plugins(attr_plugins)

    def add_members(self, members):
        """Currently unused method."""

        for member in members:
            if member not in self._members:
                self._members.append(member)

    def serialize_for_remote(self):
        """Serialize object into data to be possible recreated object.

        Returns:
            Dict[str, Any]: Serialized data.
        """

        creator_attr_defs = self.creator_attributes.get_serialized_attr_defs()
        publish_attributes = self.publish_attributes.serialize_attributes()
        return {
            "data": self.data_to_store(),
            "orig_data": self.origin_data,
            "creator_attr_defs": creator_attr_defs,
            "publish_attributes": publish_attributes,
            "creator_label": self._creator_label,
            "group_label": self._group_label,
        }

    @classmethod
    def deserialize_on_remote(cls, serialized_data):
        """Convert instance data to CreatedInstance.

        This is fake instance in remote process e.g. in UI process. The creator
        is not a full creator and should not be used for calling methods when
        instance is created from this method (matters on implementation).

        Args:
            serialized_data (Dict[str, Any]): Serialized data for remote
                recreating. Should contain 'data' and 'orig_data'.
        """

        instance_data = copy.deepcopy(serialized_data["data"])
        creator_identifier = instance_data["creator_identifier"]

        product_type = instance_data["productType"]
        product_name = instance_data.get("productName", None)

        creator_label = serialized_data["creator_label"]
        group_label = serialized_data["group_label"]
        creator_attr_defs = deserialize_attr_defs(
            serialized_data["creator_attr_defs"]
        )
        publish_attributes = serialized_data["publish_attributes"]

        obj = cls(
            product_type,
            product_name,
            instance_data,
            creator_identifier=creator_identifier,
            creator_label=creator_label,
            group_label=group_label,
            creator_attr_defs=creator_attr_defs
        )
        obj._orig_data = serialized_data["orig_data"]
        obj.publish_attributes.deserialize_attributes(publish_attributes)

        return obj

    # Context validation related methods/properties
    @property
    def has_set_folder(self):
        """Folder path is set in data."""

        return "folderPath" in self._data

    @property
    def has_set_task(self):
        """Task name is set in data."""

        return "task" in self._data

    @property
    def has_valid_context(self):
        """Context data are valid for publishing."""

        return self.has_valid_folder and self.has_valid_task

    @property
    def has_valid_folder(self):
        """Folder set in context exists in project."""

        if not self.has_set_folder:
            return False
        return self._folder_is_valid

    @property
    def has_valid_task(self):
        """Task set in context exists in project."""

        if not self.has_set_task:
            return False
        return self._task_is_valid

    def set_folder_invalid(self, invalid):
        # TODO replace with `set_folder_path`
        self._folder_is_valid = not invalid

    def set_task_invalid(self, invalid):
        # TODO replace with `set_task_name`
        self._task_is_valid = not invalid
