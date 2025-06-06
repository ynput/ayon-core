"""Abstract base classes for loader tool."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, TypedDict

from ayon_core.lib.attribute_definitions import (
    AbstractAttrDef,
    deserialize_attr_defs,
    serialize_attr_defs,
)

IconData = TypedDict("IconData", {
    "type": str,
    "name": str,
    "color": str
})

ProductBaseTypeItemData = TypedDict("ProductBaseTypeItemData", {
    "name": str,
    "icon": IconData
})


VersionItemData = TypedDict("VersionItemData", {
    "version_id": str,
    "version": int,
    "is_hero": bool,
    "product_id": str,
    "task_id": Optional[str],
    "thumbnail_id": Optional[str],
    "published_time": Optional[str],
    "author": Optional[str],
    "status": Optional[str],
    "frame_range": Optional[str],
    "duration": Optional[int],
    "handles": Optional[str],
    "step": Optional[int],
    "comment": Optional[str],
    "source": Optional[str]
})


ProductItemData = TypedDict("ProductItemData", {
    "product_id": str,
    "product_type": str,
    "product_base_type": str,
    "product_name": str,
    "product_icon": IconData,
    "product_type_icon": IconData,
    "product_base_type_icon": IconData,
    "group_name": str,
    "folder_id": str,
    "folder_label": str,
    "version_items": dict[str, VersionItemData],
    "product_in_scene": bool
})


class ProductTypeItem:
    """Item representing product type.

    Args:
        name (str): Product type name.
        icon (IconData): Product type icon definition.
    """

    def __init__(self, name: str, icon: IconData):
        self.name = name
        self.icon = icon

    def to_data(self):
        return {
            "name": self.name,
            "icon": self.icon,
        }

    @classmethod
    def from_data(cls, data):
        return cls(**data)


class ProductBaseTypeItem:
    """Item representing the product base type."""

    def __init__(self, name: str, icon: IconData):
        """Initialize product base type item."""
        self.name = name
        self.icon = icon

    def to_data(self) -> ProductBaseTypeItemData:
        """Convert item to data dictionary.

        Returns:
            ProductBaseTypeItemData: Data representation of the item.

        """
        return {
            "name": self.name,
            "icon": self.icon,
        }

    @classmethod
    def from_data(
            cls, data: ProductBaseTypeItemData) -> ProductBaseTypeItem:
        """Create item from data dictionary.

        Args:
            data (ProductBaseTypeItemData): Data to create item from.

        Returns:
            ProductBaseTypeItem: Item created from the provided data.

        """
        return cls(**data)


class ProductItem:
    """Product item with it versions.

    Args:
        product_id (str): Product id.
        product_type (str): Product type.
        product_name (str): Product name.
        product_icon (IconData): Product icon definition.
        product_type_icon (IconData): Product type icon definition.
        product_in_scene (bool): Is product in scene (only when used in DCC).
        group_name (str): Group name.
        folder_id (str): Folder id.
        folder_label (str): Folder label.
        version_items (dict[str, VersionItem]): Version items by id.
    """

    def __init__(
        self,
        product_id: str,
        product_type: str,
        product_base_type: str,
        product_name: str,
        product_icon: IconData,
        product_type_icon: IconData,
        product_base_type_icon: IconData,
        group_name: str,
        folder_id: str,
        folder_label: str,
        version_items: dict[str, VersionItem],
        *,
        product_in_scene: bool,
    ):
        self.product_id = product_id
        self.product_type = product_type
        self.product_base_type = product_base_type
        self.product_name = product_name
        self.product_icon = product_icon
        self.product_type_icon = product_type_icon
        self.product_base_type_icon = product_base_type_icon
        self.product_in_scene = product_in_scene
        self.group_name = group_name
        self.folder_id = folder_id
        self.folder_label = folder_label
        self.version_items = version_items

    def to_data(self) -> ProductItemData:
        return {
            "product_id": self.product_id,
            "product_type": self.product_type,
            "product_base_type": self.product_base_type,
            "product_name": self.product_name,
            "product_icon": self.product_icon,
            "product_type_icon": self.product_type_icon,
            "product_base_type_icon": self.product_base_type_icon,
            "product_in_scene": self.product_in_scene,
            "group_name": self.group_name,
            "folder_id": self.folder_id,
            "folder_label": self.folder_label,
            "version_items": {
                version_id: version_item.to_data()
                for version_id, version_item in self.version_items.items()
            },
        }

    @classmethod
    def from_data(cls, data):
        version_items = {
            version_id: VersionItem.from_data(version)
            for version_id, version in data["version_items"].items()
        }
        data["version_items"] = version_items
        return cls(**data)


class VersionItem:
    """Version item.

    Object have implemented comparison operators to be sortable.

    Args:
        version_id (str): Version id.
        version (int): Version. Can be negative when is hero version.
        is_hero (bool): Is hero version.
        product_id (str): Product id.
        task_id (Union[str, None]): Task id.
        thumbnail_id (Union[str, None]): Thumbnail id.
        published_time (Union[str, None]): Published time in format
            '%Y%m%dT%H%M%SZ'.
        status (Union[str, None]): Status name.
        author (Union[str, None]): Author.
        frame_range (Union[str, None]): Frame range.
        duration (Union[int, None]): Duration.
        handles (Union[str, None]): Handles.
        step (Union[int, None]): Step.
        comment (Union[str, None]): Comment.
        source (Union[str, None]): Source.
    """

    def __init__(
        self,
        *,
        version_id: str,
        version: int,
        is_hero: bool,
        product_id: str,
        task_id: Optional[str] = None,
        thumbnail_id: Optional[str] = None,
        published_time: Optional[str] = None,
        author: Optional[str] = None,
        status: Optional[str] = None,
        frame_range: Optional[str] = None,
        duration: Optional[int] = None,
        handles: Optional[str] = None,
        step: Optional[int] = None,
        comment: Optional[str] = None,
        source: Optional[str] = None,
    ):
        self.version_id = version_id
        self.product_id = product_id
        self.task_id = task_id
        self.thumbnail_id = thumbnail_id
        self.version = version
        self.is_hero = is_hero
        self.published_time = published_time
        self.author = author
        self.status = status
        self.frame_range = frame_range
        self.duration = duration
        self.handles = handles
        self.step = step
        self.comment = comment
        self.source = source

    def __eq__(self, other):
        if not isinstance(other, VersionItem):
            return False
        return (
            self.is_hero == other.is_hero
            and self.version == other.version
            and self.version_id == other.version_id
            and self.product_id == other.product_id
            and self.task_id == other.task_id
        )

    def __ne__(self, other):
        return not self.__eq__(other)

    def __gt__(self, other):
        if not isinstance(other, VersionItem):
            return False
        # Make sure hero versions are positive
        version = abs(self.version)
        other_version = abs(other.version)
        # Hero version is greater than non-hero
        if version == other_version:
            return not self.is_hero
        return version > other_version

    def __lt__(self, other):
        if not isinstance(other, VersionItem):
            return True
        # Make sure hero versions are positive
        version = abs(self.version)
        other_version = abs(other.version)
        # Non-hero version is lesser than hero
        if version == other_version:
            return self.is_hero
        return version < other_version

    def __ge__(self, other):
        return self.__eq__(other) or self.__gt__(other)

    def __le__(self, other):
        return self.__eq__(other) or self.__lt__(other)

    def to_data(self) -> VersionItemData:
        return {
            "version_id": self.version_id,
            "product_id": self.product_id,
            "task_id": self.task_id,
            "thumbnail_id": self.thumbnail_id,
            "version": self.version,
            "is_hero": self.is_hero,
            "published_time": self.published_time,
            "author": self.author,
            "status": self.status,
            "frame_range": self.frame_range,
            "duration": self.duration,
            "handles": self.handles,
            "step": self.step,
            "comment": self.comment,
            "source": self.source,
        }

    @classmethod
    def from_data(cls, data: VersionItemData):
        return cls(**data)


class RepreItem:
    """Representation item.

    Args:
        representation_id (str): Representation id.
        representation_name (str): Representation name.
        representation_icon (dict[str, Any]): Representation icon definition.
        product_name (str): Product name.
        folder_label (str): Folder label.
    """

    def __init__(
        self,
        representation_id,
        representation_name,
        representation_icon,
        product_name,
        folder_label
    ):
        self.representation_id = representation_id
        self.representation_name = representation_name
        self.representation_icon = representation_icon
        self.product_name = product_name
        self.folder_label = folder_label

    def to_data(self):
        return {
            "representation_id": self.representation_id,
            "representation_name": self.representation_name,
            "representation_icon": self.representation_icon,
            "product_name": self.product_name,
            "folder_label": self.folder_label,
        }

    @classmethod
    def from_data(cls, data):
        return cls(**data)


class ActionItem:
    """Action item that can be triggered.

    Action item is defined for a specific context. To trigger the action
    use 'identifier' and context, it necessary also use 'options'.

    Args:
        identifier (str): Action identifier.
        label (str): Action label.
        icon (dict[str, Any]): Action icon definition.
        tooltip (str): Action tooltip.
        options (Union[list[AbstractAttrDef], list[qargparse.QArgument]]):
            Action options. Note: 'qargparse' is considered as deprecated.
        order (int): Action order.
        project_name (str): Project name.
        folder_ids (list[str]): Folder ids.
        product_ids (list[str]): Product ids.
        version_ids (list[str]): Version ids.
        representation_ids (list[str]): Representation ids.
    """

    def __init__(
        self,
        identifier,
        label,
        icon,
        tooltip,
        options,
        order,
        project_name,
        folder_ids,
        product_ids,
        version_ids,
        representation_ids,
    ):
        self.identifier = identifier
        self.label = label
        self.icon = icon
        self.tooltip = tooltip
        self.options = options
        self.order = order
        self.project_name = project_name
        self.folder_ids = folder_ids
        self.product_ids = product_ids
        self.version_ids = version_ids
        self.representation_ids = representation_ids

    def _options_to_data(self):
        options = self.options
        if not options:
            return options
        if isinstance(options[0], AbstractAttrDef):
            return serialize_attr_defs(options)
        # NOTE: Data conversion is not used by default in loader tool. But for
        #   future development of detached UI tools it would be better to be
        #   prepared for it.
        raise NotImplementedError(
            "{}.to_data is not implemented. Use Attribute definitions"
            " from 'ayon_core.lib' instead of 'qargparse'.".format(
                self.__class__.__name__
            )
        )

    def to_data(self):
        options = self._options_to_data()
        return {
            "identifier": self.identifier,
            "label": self.label,
            "icon": self.icon,
            "tooltip": self.tooltip,
            "options": options,
            "order": self.order,
            "project_name": self.project_name,
            "folder_ids": self.folder_ids,
            "product_ids": self.product_ids,
            "version_ids": self.version_ids,
            "representation_ids": self.representation_ids,
        }

    @classmethod
    def from_data(cls, data):
        options = data["options"]
        if options:
            options = deserialize_attr_defs(options)
        data["options"] = options
        return cls(**data)


class ProductTypesFilter:
    """Product types filter.

    Defines the filtering for product types.
    """
    def __init__(self, product_types: List[str], is_allow_list: bool):
        self.product_types: List[str] = product_types
        self.is_allow_list: bool = is_allow_list


class _BaseLoaderController(ABC):
    """Base loader controller abstraction.

    Abstract base class that is required for both frontend and backed.
    """

    @abstractmethod
    def get_current_context(self):
        """Current context is a context of the current scene.

        Example output:
            {
                "project_name": "MyProject",
                "folder_id": "0011223344-5566778-99",
                "task_name": "Compositing",
            }

        Returns:
            dict[str, Union[str, None]]: Context data.
        """

        pass

    @abstractmethod
    def reset(self):
        """Reset all cached data to reload everything.

        Triggers events "controller.reset.started" and
        "controller.reset.finished".
        """

        pass

    # Model wrappers
    @abstractmethod
    def get_folder_items(self, project_name, sender=None):
        """Folder items for a project.

        Args:
            project_name (str): Project name.
            sender (Optional[str]): Sender who requested the name.

        Returns:
            list[FolderItem]: Folder items for the project.
        """

        pass

    # Expected selection helpers
    @abstractmethod
    def get_expected_selection_data(self):
        """Full expected selection information.

        Expected selection is a selection that may not be yet selected in UI
        e.g. because of refreshing, this data tell the UI what should be
        selected when they finish their refresh.

        Returns:
            dict[str, Any]: Expected selection data.
        """

        pass

    @abstractmethod
    def set_expected_selection(self, project_name, folder_id):
        """Set expected selection.

        Args:
            project_name (str): Name of project to be selected.
            folder_id (str): Id of folder to be selected.
        """

        pass


class BackendLoaderController(_BaseLoaderController):
    """Backend loader controller abstraction.

    What backend logic requires from a controller for proper logic.
    """

    @abstractmethod
    def emit_event(self, topic, data=None, source=None):
        """Emit event with a certain topic, data and source.

        The event should be sent to both frontend and backend.

        Args:
            topic (str): Event topic name.
            data (Optional[dict[str, Any]]): Event data.
            source (Optional[str]): Event source.
        """

        pass

    @abstractmethod
    def get_loaded_product_ids(self):
        """Return set of loaded product ids.

        Returns:
            set[str]: Set of loaded product ids.
        """

        pass


class FrontendLoaderController(_BaseLoaderController):
    @abstractmethod
    def register_event_callback(self, topic, callback):
        """Register callback for an event topic.

        Args:
            topic (str): Event topic name.
            callback (func): Callback triggered when the event is emitted.
        """

        pass

    # Expected selection helpers
    @abstractmethod
    def expected_project_selected(self, project_name):
        """Expected project was selected in frontend.

        Args:
            project_name (str): Project name.
        """

        pass

    @abstractmethod
    def expected_folder_selected(self, folder_id):
        """Expected folder was selected in frontend.

        Args:
            folder_id (str): Folder id.
        """

        pass

    # Model wrapper calls
    @abstractmethod
    def get_project_items(self, sender=None):
        """Items for all projects available on server.

        Triggers event topics "projects.refresh.started" and
        "projects.refresh.finished" with data:
            {
                "sender": sender
            }

        Notes:
            Filtering of projects is done in UI.

        Args:
            sender (Optional[str]): Sender who requested the items.

        Returns:
            list[ProjectItem]: List of project items.
        """

        pass

    @abstractmethod
    def get_folder_type_items(self, project_name, sender=None):
        """Folder type items for a project.

        This function may trigger events with topics
        'projects.folder_types.refresh.started' and
        'projects.folder_types.refresh.finished' which will contain 'sender'
        value in data.
        That may help to avoid re-refresh of items in UI elements.

        Args:
            project_name (str): Project name.
            sender (str): Who requested folder type items.

        Returns:
            list[FolderTypeItem]: Folder type information.

        """
        pass

    @abstractmethod
    def get_task_items(self, project_name, folder_ids, sender=None):
        """Task items for folder ids.

        Args:
            project_name (str): Project name.
            folder_ids (Iterable[str]): Folder ids.
            sender (Optional[str]): Sender who requested the items.

        Returns:
            list[TaskItem]: List of task items.

        """
        pass

    @abstractmethod
    def get_task_type_items(self, project_name, sender=None):
        """Task type items for a project.

        This function may trigger events with topics
        'projects.task_types.refresh.started' and
        'projects.task_types.refresh.finished' which will contain 'sender'
        value in data.
        That may help to avoid re-refresh of items in UI elements.

        Args:
            project_name (str): Project name.
            sender (str): Who requested task type items.

        Returns:
            list[TaskTypeItem]: Task type information.

        """
        pass

    @abstractmethod
    def get_folder_labels(self, project_name, folder_ids):
        """Get folder labels for folder ids.

        Args:
            project_name (str): Project name.
            folder_ids (Iterable[str]): Folder ids.

        Returns:
            dict[str, Optional[str]]: Folder labels by folder id.

        """
        pass

    @abstractmethod
    def get_project_status_items(self, project_name, sender=None):
        """Items for all projects available on server.

        Triggers event topics "projects.statuses.refresh.started" and
        "projects.statuses.refresh.finished" with data:
            {
                "sender": sender,
                "project_name": project_name
            }

        Args:
            project_name (Union[str, None]): Project name.
            sender (Optional[str]): Sender who requested the items.

        Returns:
            list[StatusItem]: List of status items.
        """

        pass

    @abstractmethod
    def get_product_items(self, project_name, folder_ids, sender=None):
        """Product items for folder ids.

        Triggers event topics "products.refresh.started" and
        "products.refresh.finished" with data:
            {
                "project_name": project_name,
                "folder_ids": folder_ids,
                "sender": sender
            }

        Args:
            project_name (str): Project name.
            folder_ids (Iterable[str]): Folder ids.
            sender (Optional[str]): Sender who requested the items.

        Returns:
            list[ProductItem]: List of product items.
        """

        pass

    @abstractmethod
    def get_product_item(self, project_name, product_id):
        """Receive single product item.

        Args:
            project_name (str): Project name.
            product_id (str): Product id.

        Returns:
             Union[ProductItem, None]: Product info or None if not found.
        """

        pass

    @abstractmethod
    def get_product_type_items(self, project_name):
        """Product type items for a project.

        Product types have defined if are checked for filtering or not.

        Args:
            project_name (Union[str, None]): Project name.

        Returns:
            list[ProductTypeItem]: List of product type items for a project.
        """

        pass

    @abstractmethod
    def get_representation_items(
        self, project_name, version_ids, sender=None
    ):
        """Representation items for version ids.

        Triggers event topics "model.representations.refresh.started" and
        "model.representations.refresh.finished" with data:
            {
                "project_name": project_name,
                "version_ids": version_ids,
                "sender": sender
            }

        Args:
            project_name (str): Project name.
            version_ids (Iterable[str]): Version ids.
            sender (Optional[str]): Sender who requested the items.

        Returns:
            list[RepreItem]: List of representation items.
        """

        pass

    @abstractmethod
    def get_version_thumbnail_ids(self, project_name, version_ids):
        """Get thumbnail ids for version ids.

        Args:
            project_name (str): Project name.
            version_ids (Iterable[str]): Version ids.

        Returns:
            dict[str, Union[str, Any]]: Thumbnail id by version id.
        """

        pass

    @abstractmethod
    def get_folder_thumbnail_ids(self, project_name, folder_ids):
        """Get thumbnail ids for folder ids.

        Args:
            project_name (str): Project name.
            folder_ids (Iterable[str]): Folder ids.

        Returns:
            dict[str, Union[str, Any]]: Thumbnail id by folder id.
        """

        pass

    @abstractmethod
    def get_versions_representation_count(
        self, project_name, version_ids, sender=None
    ):
        """
        Args:
            project_name (str): Project name.
            version_ids (Iterable[str]): Version ids.
            sender (Optional[str]): Sender who requested the items.

        Returns:
            dict[str, int]: Representation count by version id.
        """

        pass

    @abstractmethod
    def get_thumbnail_paths(
        self,
        project_name,
        entity_type,
        entity_ids
    ):
        """Get thumbnail path for thumbnail id.

        This method should get a path to a thumbnail based on thumbnail id.
        Which probably means to download the thumbnail from server and store
        it locally.

        Args:
            project_name (str): Project name.
            entity_type (str): Entity type.
            entity_ids (set[str]): Entity ids.

        Returns:
            dict[str, Union[str, None]]: Thumbnail path by entity id.
        """

        pass

    # Selection model wrapper calls
    @abstractmethod
    def get_selected_project_name(self):
        """Get selected project name.

        The information is based on last selection from UI.

        Returns:
            Union[str, None]: Selected project name.
        """

        pass

    @abstractmethod
    def get_selected_folder_ids(self):
        """Get selected folder ids.

        The information is based on last selection from UI.

        Returns:
            list[str]: Selected folder ids.

        """
        pass

    @abstractmethod
    def get_selected_task_ids(self):
        """Get selected task ids.

        The information is based on last selection from UI.

        Returns:
            list[str]: Selected folder ids.

        """
        pass

    @abstractmethod
    def set_selected_tasks(self, task_ids):
        """Set selected tasks.

        Args:
            task_ids (Iterable[str]): Selected task ids.

        """
        pass

    @abstractmethod
    def get_selected_version_ids(self):
        """Get selected version ids.

        The information is based on last selection from UI.

        Returns:
            list[str]: Selected version ids.

        """
        pass

    @abstractmethod
    def get_selected_representation_ids(self):
        """Get selected representation ids.

        The information is based on last selection from UI.

        Returns:
            list[str]: Selected representation ids.
        """

        pass

    @abstractmethod
    def set_selected_project(self, project_name):
        """Set selected project.

        Project selection changed in UI. Method triggers event with topic
        "selection.project.changed" with data:
            {
                "project_name": self._project_name
            }

        Args:
            project_name (Union[str, None]): Selected project name.
        """

        pass

    @abstractmethod
    def set_selected_folders(self, folder_ids):
        """Set selected folders.

        Folder selection changed in UI. Method triggers event with topic
        "selection.folders.changed" with data:
            {
                "project_name": project_name,
                "folder_ids": folder_ids
            }

        Args:
            folder_ids (Iterable[str]): Selected folder ids.
        """

        pass

    @abstractmethod
    def set_selected_versions(self, version_ids):
        """Set selected versions.

        Version selection changed in UI. Method triggers event with topic
        "selection.versions.changed" with data:
            {
                "project_name": project_name,
                "folder_ids": folder_ids,
                "version_ids": version_ids
            }

        Args:
            version_ids (Iterable[str]): Selected version ids.
        """

        pass

    @abstractmethod
    def set_selected_representations(self, repre_ids):
        """Set selected representations.

        Representation selection changed in UI. Method triggers event with
        topic "selection.representations.changed" with data:
            {
                "project_name": project_name,
                "folder_ids": folder_ids,
                "version_ids": version_ids,
                "representation_ids": representation_ids
            }

        Args:
            repre_ids (Iterable[str]): Selected representation ids.
        """

        pass

    # Load action items
    @abstractmethod
    def get_versions_action_items(self, project_name, version_ids):
        """Action items for versions selection.

        Args:
            project_name (str): Project name.
            version_ids (Iterable[str]): Version ids.

        Returns:
            list[ActionItem]: List of action items.
        """

        pass

    @abstractmethod
    def get_representations_action_items(
        self, project_name, representation_ids
    ):
        """Action items for representations selection.

        Args:
            project_name (str): Project name.
            representation_ids (Iterable[str]): Representation ids.

        Returns:
            list[ActionItem]: List of action items.
        """

        pass

    @abstractmethod
    def trigger_action_item(
        self,
        identifier,
        options,
        project_name,
        version_ids,
        representation_ids
    ):
        """Trigger action item.

        Triggers event "load.started" with data:
            {
                "identifier": identifier,
                "id": <Random UUID>,
            }

        And triggers "load.finished" with data:
            {
                "identifier": identifier,
                "id": <Random UUID>,
                "error_info": [...],
            }

        Args:
            identifier (str): Action identifier.
            options (dict[str, Any]): Action option values from UI.
            project_name (str): Project name.
            version_ids (Iterable[str]): Version ids.
            representation_ids (Iterable[str]): Representation ids.
        """

        pass

    @abstractmethod
    def change_products_group(self, project_name, product_ids, group_name):
        """Change group of products.

        Triggers event "products.group.changed" with data:
            {
                "project_name": project_name,
                "folder_ids": folder_ids,
                "product_ids": product_ids,
                "group_name": group_name,
            }

        Args:
            project_name (str): Project name.
            product_ids (Iterable[str]): Product ids.
            group_name (str): New group name.
        """

        pass

    @abstractmethod
    def fill_root_in_source(self, source):
        """Fill root in source path.

        Args:
            source (Union[str, None]): Source of a published version. Usually
                rootless workfile path.
        """

        pass

    # NOTE: Methods 'is_loaded_products_supported' and
    #   'is_standard_projects_filter_enabled' are both based on being in host
    #   or not. Maybe we could implement only single method 'is_in_host'?
    @abstractmethod
    def is_loaded_products_supported(self):
        """Is capable to get information about loaded products.

        Returns:
            bool: True if it is supported.
        """

        pass

    @abstractmethod
    def is_standard_projects_filter_enabled(self):
        """Is standard projects filter enabled.

        This is used for filtering out when loader tool is used in a host. In
        that case only current project and library projects should be shown.

        Returns:
            bool: Frontend should filter out non-library projects, except
                current context project.
        """

        pass

    # Site sync functions
    @abstractmethod
    def is_sitesync_enabled(self, project_name=None):
        """Is site sync enabled.

        Site sync addon can be enabled but can be disabled per project.

        When asked for enabled state without project name, it should return
            True if site sync addon is available and enabled.

        Args:
            project_name (Optional[str]): Project name.

        Returns:
            bool: True if site sync is enabled.
        """

        pass

    @abstractmethod
    def get_active_site_icon_def(self, project_name):
        """Active site icon definition.

        Args:
            project_name (Union[str, None]): Project name.

        Returns:
            Union[dict[str, Any], None]: Icon definition or None if site sync
                is not enabled for the project.
        """

        pass

    @abstractmethod
    def get_remote_site_icon_def(self, project_name):
        """Remote site icon definition.

        Args:
            project_name (Union[str, None]): Project name.

        Returns:
            Union[dict[str, Any], None]: Icon definition or None if site sync
                is not enabled for the project.
        """

        pass

    @abstractmethod
    def get_version_sync_availability(self, project_name, version_ids):
        """Version sync availability.

        Args:
            project_name (str): Project name.
            version_ids (Iterable[str]): Version ids.

        Returns:
            dict[str, tuple[int, int]]: Sync availability by version id.
        """

        pass

    @abstractmethod
    def get_representations_sync_status(
        self, project_name, representation_ids
    ):
        """Representations sync status.

        Args:
            project_name (str): Project name.
            representation_ids (Iterable[str]): Representation ids.

        Returns:
            dict[str, tuple[int, int]]: Sync status by representation id.
        """

        pass

    @abstractmethod
    def get_product_types_filter(self):
        """Return product type filter for current context.

        Returns:
            ProductTypesFilter: Product type filter for current context
        """

        pass
