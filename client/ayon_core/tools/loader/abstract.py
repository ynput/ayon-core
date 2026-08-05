"""Abstract base classes for loader tool."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable, Any, Optional, Union

from ayon_core.lib.icon_definitions import (
    IconBase,
    AwesomeFontIcon,
    get_icon_def_from_data,
)
from ayon_core.lib.attribute_definitions import (
    AbstractAttrDef,
    deserialize_attr_defs,
    serialize_attr_defs,
)
from ayon_core.tools.common_models import (
    TaskItem,
    TagItem,
    ProductTypeIconMapping,
)


@dataclass
class ProductTypeItem:
    """Item representing product type.

    Args:
        name (str): Product type name.
        icon (dict[str, Any]): Product type icon definition.
    """
    name: str
    icon: dict[str, Any]

    def to_data(self):
        return dict(name=self.name, icon=self.icon)

    @classmethod
    def from_data(cls, data):
        return cls(**data)


@dataclass
class ProductBaseTypeItem:
    """Item representing the product base type."""
    name: str
    icon: AwesomeFontIcon

    def to_data(self) -> dict[str, Any]:
        """Convert item to data dictionary.

        Returns:
            dict[str, Any]: Data representation of the item.

        """
        return {
            "name": self.name,
            "icon": {
                "name": self.icon.name,
                "color": self.icon.color,
            },
        }

    @classmethod
    def from_data(
        cls, data: dict[str, Any]
    ) -> ProductBaseTypeItem:
        """Create item from data dictionary.

        Args:
            data (dict[str, Any]): Data to create item from.

        Returns:
            ProductBaseTypeItem: Item created from the provided data.

        """
        icon = data["icon"]
        data["icon"] = AwesomeFontIcon(icon["name"], color=icon["color"])
        return cls(**data)


@dataclass
class ProductItem:
    """Product item with it versions.

    Attributes:
        product_id (str): Product id.
        product_type (str): Product type.
        product_name (str): Product name.
        product_icon (dict[str, Any]): Product icon definition.
        product_in_scene (bool): Is product in scene (only when used in DCC).
        group_name (str | None]): Group name.
        folder_id (str): Folder id.
        folder_label (str): Folder label.
        version_items (dict[str, VersionItem]): Version items by id.
    """
    product_id: str
    product_type: str
    product_base_type: str
    product_name: str
    product_icon: dict[str, Any]
    group_name: str | None
    folder_id: str
    folder_label: str
    version_items: dict[str, VersionItem]
    product_in_scene: bool

    def to_data(self) -> dict[str, Any]:
        return dict(
            product_id=self.product_id,
            product_type=self.product_type,
            product_base_type=self.product_base_type,
            product_name=self.product_name,
            product_icon=self.product_icon,
            product_in_scene=self.product_in_scene,
            group_name=self.group_name,
            folder_id=self.folder_id,
            folder_label=self.folder_label,
            version_items={
                version_id: version_item.to_data()
                for version_id, version_item in self.version_items.items()
            },
        )

    @classmethod
    def from_data(cls, data):
        version_items = {
            version_id: VersionItem.from_data(version)
            for version_id, version in data["version_items"].items()
        }
        data["version_items"] = version_items
        return cls(**data)


@dataclass
class VersionItem:
    """Version item.

    Object have implemented comparison operators to be sortable.

    Attributes:
        version_id (str): Version id.
        version (int): Version. Can be negative when is hero version.
        is_hero (bool): Is hero version.
        product_id (str): Product id.
        task_id (str | None): Task id.
        thumbnail_id (str | None): Thumbnail id.
        published_time (str | None): Published time in format
            '%Y%m%dT%H%M%SZ'.
        status (str | None): Status name.
        tags (list[str] | None): Tags.
        author (str | None): Author.
        frame_range (str | None): Frame range.
        duration (int | None): Duration.
        handles (str | None): Handles.
        step (int | None): Step.
        comment (str | None): Comment.
        source (str | None): Source.

    """
    version_id: str
    version: int
    is_hero: bool
    product_id: str
    task_id: str | None
    thumbnail_id: str | None
    published_time: str | None
    tags: list[str] | None
    author: str | None
    status: str | None
    frame_range: str | None
    duration: int | None
    handles: str | None
    step: int | None
    comment: str | None
    source: str | None

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

    def to_data(self) -> dict[str, Any]:
        return dict(
            version_id=self.version_id,
            product_id=self.product_id,
            task_id=self.task_id,
            thumbnail_id=self.thumbnail_id,
            version=self.version,
            is_hero=self.is_hero,
            published_time=self.published_time,
            author=self.author,
            tags=self.tags,
            status=self.status,
            frame_range=self.frame_range,
            duration=self.duration,
            handles=self.handles,
            step=self.step,
            comment=self.comment,
            source=self.source,
        )

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> VersionItem:
        return cls(**data)


@dataclass
class RepreItem:
    """Representation item.

    Attributes:
        representation_id (str): Representation id.
        representation_name (str): Representation name.
        representation_icon (IconBase): Representation icon definition.
        product_name (str): Product name.
        folder_label (str): Folder label.
    """

    representation_id: str
    representation_name: str
    representation_icon: IconBase
    product_name: str
    folder_label: str

    def to_data(self) -> dict[str, Any]:
        return dict(
            representation_id=self.representation_id,
            representation_name=self.representation_name,
            representation_icon=self.representation_icon.to_data(),
            product_name=self.product_name,
            folder_label=self.folder_label,
        )

    @classmethod
    def from_data(cls, data) -> RepreItem:
        data["representation_icon"] = get_icon_def_from_data(
            data["representation_icon"]
        )
        return cls(**data)


@dataclass
class ActionItem:
    """Action item that can be triggered.

    Action item is defined for a specific context. To trigger the action
    use 'identifier' and context, it necessary also use 'options'.

    Args:
        identifier (str): Action identifier.
        label (str): Action label.
        group_label (str | None): Group label.
        icon (IconBase | dict[str, Any] | None): Action icon definition.
        tooltip (str | None): Action tooltip.
        order (int): Action order.
        data (dict[str, Any] | None): Additional action data.
        options (list[AbstractAttrDef] | None):
            Action options. Note: 'qargparse' is considered as deprecated.

    """
    identifier: str
    label: str
    group_label: str | None
    icon: IconBase | dict[str, Any] | None
    tooltip: str | None
    order: int
    data: dict[str, Any] | None
    options: list[AbstractAttrDef] | None

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
            f"{self.__class__.__name__}.to_data is not implemented."
            " Use Attribute definitions from 'ayon_core.lib'"
            " instead of 'qargparse'."
        )

    def to_data(self) -> dict[str, Any]:
        options = self._options_to_data()
        return dict(
            identifier=self.identifier,
            label=self.label,
            group_label=self.group_label,
            icon=self.icon,
            tooltip=self.tooltip,
            order=self.order,
            data=self.data,
            options=options,
        )

    @classmethod
    def from_data(cls, data) -> "ActionItem":
        options = data["options"]
        if options:
            options = deserialize_attr_defs(options)
        data["options"] = options
        return cls(**data)


@dataclass
class ProductTypesFilter:
    """Product types filter.

    Defines the filtering for product types.
    """
    product_types: list[str]
    is_allow_list: bool

    def to_data(self) -> dict[str, Any]:
        return dict(
            product_types=self.product_types,
            is_allow_list=self.is_allow_list,
        )

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> ProductTypesFilter:
        return cls(**data)


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
            dict[str, FolderItem]: Folder items for the project.
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

    @abstractmethod
    def get_project_settings(self, project_name: str | None) -> dict:
        pass

    @abstractmethod
    def get_product_type_icons_mapping(
        self, project_name: Optional[str]
    ) -> ProductTypeIconMapping:
        """Product type icons mapping.

        Returns:
            ProductTypeIconMapping: Product type icons mapping.

        """
        pass


class FrontendLoaderController(_BaseLoaderController):
    @abstractmethod
    def get_window_subtitle(self) -> Optional[str]:
        """Get window subtitle.

        Returns:
            Optional[str]: Window subtitle.

        """

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
    def get_project_anatomy_tags(self, project_name: str) -> list[TagItem]:
        """Tag items defined on project anatomy.

        Args:
            project_name (str): Project name.

        Returns:
            list[TagItem]: Tag definition items.

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
    def get_task_items(
        self,
        project_name: str,
        folder_ids: Iterable[str],
        sender: Optional[str] = None,
    ) -> list[TaskItem]:
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
    def get_my_tasks_entity_ids(
        self, project_name: str
    ) -> dict[str, list[str]]:
        """Get entity ids for my tasks.

        Args:
            project_name (str): Project name.

        Returns:
            dict[str, list[str]]: Folder and task ids.

        """
        pass

    @abstractmethod
    def get_available_tags_by_entity_type(
        self, project_name: str
    ) -> dict[str, list[str]]:
        """Get available tags by entity type.

        Args:
            project_name (str): Project name.

        Returns:
            dict[str, list[str]]: Available tags by entity type.

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
    def get_action_items(
        self,
        project_name: str,
        entity_ids: set[str],
        entity_type: str,
    ) -> list[ActionItem]:
        """Action items for versions selection.

        Args:
            project_name (str): Project name.
            entity_ids (set[str]): Entity ids.
            entity_type (str): Entity type.

        Returns:
            list[ActionItem]: List of action items.

        """
        pass

    @abstractmethod
    def trigger_action_item(
        self,
        identifier: str,
        project_name: str,
        selected_ids: set[str],
        selected_entity_type: str,
        data: Optional[dict[str, Any]],
        options: dict[str, Any],
        form_values: dict[str, Any],
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
            identifier (sttr): Plugin identifier.
            project_name (str): Project name.
            selected_ids (set[str]): Selected entity ids.
            selected_entity_type (str): Selected entity type.
            data (Optional[dict[str, Any]]): Additional action item data.
            options (dict[str, Any]): Action option values from UI.
            form_values (dict[str, Any]): Action form values from UI.

        """
        pass

    @abstractmethod
    def change_products_group(
        self,
        project_name: str,
        product_ids: set[str],
        group_name: str,
    ):
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
    def get_active_site(self, project_name: str) -> str | None:
        """Active site name.

        Args:
            project_name (str): Project name.

        Returns:
            Union[str, None]: Site name or None if site sync is not enabled.

        """
        pass

    @abstractmethod
    def get_remote_site(self, project_name: str) -> str | None:
        """Remote site name.

        Args:
            project_name (str): Project name.

        Returns:
            Union[str, None]: Site name or None if site sync is not enabled.

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
