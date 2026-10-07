"""Fetch entity activities (comments, publishes, status changes)."""

from __future__ import annotations

import tempfile
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

import ayon_api

from ayon_core.lib import Logger
from ayon_core.ui.data_models import (
    CommentModel,
    ProjectData,
    StatusChangeModel,
    User,
    VersionPublishModel,
)
from ayon_core.ui.image_cache import ImageCache
from ayon_core.ui.utils import process_activity_data

log = Logger.get_logger(__name__)

ACTIVITY_TYPES = ("comment", "version.publish", "status.change")
# 'origin' are activities made on the entity itself, 'mention' are comments
#   mentioning it and 'relation' are activities of related entities, e.g.
#   versions published from a task.
REFERENCE_TYPES = ("origin", "mention", "relation")
ACTIVITY_FIELDS = (
    "activityId",
    "activityType",
    "activityData",
    "body",
    "createdAt",
    "updatedAt",
    "author.name",
    "files.id",
    "files.mime",
)


def get_version_thumbnail_path(key: str) -> str:
    """Download a version thumbnail, or get it from the image cache.

    Meant to be called outside of the main thread. The key format is
    shared with the Browser tool so both use the same cached files.

    Args:
        key: Key as ``"<project_name>/<version_id>/<thumbnail_id>"``.

    Returns:
        Path to the image file, empty string if it is not available.
    """
    parts = key.split("/", 2) if key else []
    if len(parts) != 3 or not all(parts):
        return ""

    def _fetch() -> str:
        content = ayon_api.get_version_thumbnail(*parts)
        if not content.is_valid:
            return ""
        is_jpeg = content.content_type and "jpeg" in content.content_type
        with tempfile.NamedTemporaryFile(
            suffix=".jpg" if is_jpeg else ".png", delete=False
        ) as stream:
            stream.write(content.content)
            return stream.name

    try:
        return ImageCache.get_instance().get(key, _fetch)
    except Exception:
        log.debug("Failed to fetch thumbnail %r", key, exc_info=True)
        return ""


@dataclass
class ActivityFileItem:
    """File attached to a comment.

    Attributes:
        file_id: Id of the file.
        mime: Mime type of the file.
    """

    file_id: str | None
    mime: str | None

    def to_data(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> ActivityFileItem:
        return cls(**data)


@dataclass
class ActivityAnnotationItem:
    """Drawing over a frame of a reviewable, attached to a comment.

    Attributes:
        annotation_id: Id of the annotation.
        frame_range: Annotated frames as ``[start, end]``.
        composite: Id of the file with the annotated frame.
        transparent: Id of the file with the drawing only.
    """

    annotation_id: str | None
    frame_range: list[int] | None
    composite: str | None
    transparent: str | None

    def to_data(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> ActivityAnnotationItem:
        return cls(**data)


@dataclass
class ActivityItem:
    """Activity of an entity.

    Attributes:
        activity_id: Activity id.
        activity_type: Type of the activity, one of 'ACTIVITY_TYPES'.
        author: Username of the author, not filled e.g. for activities of
            removed users.
        body: Text of a comment.
        created_at: Date of creation in ISO format.
        updated_at: Date of the last change in ISO format.
        category: Category of a comment.
        product_name: Product of the version that was published or that
            has changed its status.
        version_name: Name of the published version, or of the entity
            that has changed its status.
        version_id: Id of the published version.
        version_status: Current status of the published version, not the
            status it had when it was published.
        thumbnail_id: Thumbnail id of the published version.
        old_status: Status before a status change.
        new_status: Status after a status change.
        files: Files attached to a comment.
        annotations: Annotations attached to a comment.
    """

    activity_id: str
    activity_type: str
    author: str | None = None
    body: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    category: str | None = None
    product_name: str | None = None
    version_name: str | None = None
    version_id: str | None = None
    version_status: str | None = None
    thumbnail_id: str | None = None
    old_status: str | None = None
    new_status: str | None = None
    files: list[ActivityFileItem] = field(default_factory=list)
    annotations: list[ActivityAnnotationItem] = field(default_factory=list)

    @classmethod
    def from_entity_data(cls, activity: dict[str, Any]) -> ActivityItem:
        """Create the item from an activity queried from the server.

        Args:
            activity: Activity with 'ACTIVITY_FIELDS'.

        Returns:
            Activity item. Status and thumbnail of a published version
                are not known to the activity.
        """
        activity_type = activity["activityType"]
        data = activity.get("activityData") or {}
        origin = data.get("origin") or {}
        kwargs: dict[str, Any] = {}
        if activity_type == "comment":
            kwargs["category"] = data.get("category")
            kwargs["files"] = [
                ActivityFileItem(file.get("id"), file.get("mime"))
                for file in activity.get("files") or []
            ]
            kwargs["annotations"] = [
                ActivityAnnotationItem(
                    annotation.get("id"),
                    annotation.get("range"),
                    annotation.get("composite"),
                    annotation.get("transparent"),
                )
                for annotation in data.get("annotations") or []
            ]
        elif activity_type == "version.publish":
            kwargs["product_name"] = (
                (data.get("context") or {}).get("productName")
            )
            kwargs["version_name"] = origin.get("name")
            kwargs["version_id"] = origin.get("id")
        elif activity_type == "status.change":
            kwargs["product_name"] = next(
                (
                    parent.get("name")
                    for parent in data.get("parents") or []
                    if parent.get("type") == "product"
                ),
                None,
            )
            kwargs["version_name"] = origin.get("name")
            kwargs["old_status"] = data.get("oldValue")
            kwargs["new_status"] = data.get("newValue")
        return cls(
            activity_id=activity["activityId"],
            activity_type=activity_type,
            # Author is not filled e.g. for activities of removed users
            author=(activity.get("author") or {}).get("name"),
            body=activity.get("body"),
            created_at=activity.get("createdAt"),
            updated_at=activity.get("updatedAt"),
            **kwargs,
        )

    def to_data(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> ActivityItem:
        kwargs = dict(data)
        kwargs["files"] = [
            ActivityFileItem.from_data(file_data)
            for file_data in data.get("files") or []
        ]
        kwargs["annotations"] = [
            ActivityAnnotationItem.from_data(annotation_data)
            for annotation_data in data.get("annotations") or []
        ]
        return cls(**kwargs)


@dataclass
class ActivityFeed:
    """Activities of entities with data needed to display them.

    Attributes:
        activities: Activities sorted from the newest to the oldest.
        statuses: Project statuses as ``AYStatusChange`` definitions.
        users: Project users.
        has_more: More activities exist than were fetched.
    """

    activities: list[
        CommentModel | VersionPublishModel | StatusChangeModel
    ] = field(default_factory=list)
    statuses: list[dict[str, Any]] = field(default_factory=list)
    users: list[User] = field(default_factory=list)
    has_more: bool = False


class ActivitiesModel:
    """Model fetching activity feeds of entities.

    Project users and statuses are cached per project, activities are
    always fetched so the feed is up to date.
    """

    def __init__(self) -> None:
        self._users_by_project: dict[str, list[User]] = {}
        self._statuses_by_project: dict[str, list[dict[str, Any]]] = {}

    def reset(self) -> None:
        """Clear cached project data."""
        self._users_by_project = {}
        self._statuses_by_project = {}

    def get_activity_items(
        self,
        project_name: str,
        entity_ids: list[str] | set[str],
        limit: int = 50,
    ) -> list[ActivityItem]:
        """Fetch the latest activities of entities.

        Queries the server, so it is meant to be called outside of the
        main thread.

        Args:
            project_name: Project name.
            entity_ids: Ids of entities to get activities for.
            limit: Maximum number of activities to fetch.

        Returns:
            Activities sorted from the newest to the oldest, empty if there
                are no entities.
        """
        entity_ids = set(entity_ids)
        if not project_name or not entity_ids:
            return []

        # The same activity is returned once per matching reference
        activities_by_id: dict[str, dict[str, Any]] = {}
        # NOTE 'limit' argument of 'get_activities' is not used because it
        #   fails in ayon_api (at least up to 1.2.22), the generator is
        #   stopped instead so only the first page is queried.
        for activity in ayon_api.get_activities(
            project_name,
            entity_ids=entity_ids,
            activity_types=ACTIVITY_TYPES,
            reference_types=REFERENCE_TYPES,
            fields=ACTIVITY_FIELDS,
            order=ayon_api.SortOrder.descending,
        ):
            if len(activities_by_id) >= limit:
                break
            activities_by_id.setdefault(activity["activityId"], activity)

        activity_items = [
            ActivityItem.from_entity_data(activity)
            for activity in activities_by_id.values()
        ]
        activity_items.sort(
            key=lambda item: item.created_at or "", reverse=True
        )
        self._fill_published_version_items(project_name, activity_items)
        return activity_items

    @staticmethod
    def _fill_published_version_items(
        project_name: str, activity_items: list[ActivityItem]
    ) -> None:
        """Fill current status and thumbnail id of published versions."""
        items_by_version_id: dict[str, list[ActivityItem]] = {}
        for item in activity_items:
            if item.version_id:
                items_by_version_id.setdefault(item.version_id, []).append(
                    item
                )
        if not items_by_version_id:
            return
        # Versions that were removed since are not returned
        for version in ayon_api.get_versions(
            project_name,
            version_ids=set(items_by_version_id),
            fields={"id", "status", "thumbnailId"},
        ):
            for item in items_by_version_id[version["id"]]:
                item.version_status = version.get("status")
                item.thumbnail_id = version.get("thumbnailId")

    def get_activity_feed(
        self,
        project_name: str,
        entity_ids: Iterable[str],
        limit: int = 50,
    ) -> ActivityFeed:
        """Fetch the latest activities of entities.

        Meant to be called outside of the main thread.

        Args:
            project_name: Project name.
            entity_ids: Ids of entities to get activities for.
            limit: Maximum number of activities to fetch.

        Returns:
            Activity feed, empty if there are no entities.
        """
        entity_ids = set(entity_ids)
        if not project_name or not entity_ids:
            return ActivityFeed()

        users = self._get_users(project_name)
        # The same activity is returned once per matching reference
        activities_by_id: dict[str, dict[str, Any]] = {}
        has_more = False
        # NOTE 'limit' argument of 'get_activities' is not used because it
        #   fails in ayon_api (at least up to 1.2.22), the generator is
        #   stopped instead so only the first page is queried.
        for activity in ayon_api.get_activities(
            project_name,
            entity_ids=entity_ids,
            activity_types=ACTIVITY_TYPES,
            reference_types=REFERENCE_TYPES,
            fields=ACTIVITY_FIELDS,
            order=ayon_api.SortOrder.descending,
        ):
            if len(activities_by_id) >= limit:
                has_more = True
                break
            # Author is not filled e.g. for activities of removed users
            if not activity.get("author"):
                activity["author"] = {}
            activities_by_id.setdefault(activity["activityId"], activity)

        activities = sorted(
            activities_by_id.values(),
            key=lambda activity: activity.get("createdAt") or "",
            reverse=True,
        )
        project_data = ProjectData(
            project_name=project_name,
            users=users,
            teams=[],
            anatomy={},
            comment_category=[],
            current_user=None,
        )
        version_ids_by_activity_id = self._get_published_version_ids(
            activities
        )
        activity_models = process_activity_data(
            {"project": {"activities": activities}}, project_data
        )
        self._fill_published_versions(
            project_name, activity_models, version_ids_by_activity_id
        )
        return ActivityFeed(
            activities=activity_models,
            statuses=self._get_statuses(project_name),
            users=users,
            has_more=has_more,
        )

    @staticmethod
    def _get_published_version_ids(
        activities: list[dict[str, Any]],
    ) -> dict[str, str]:
        """Map ids of publish activities to ids of published versions."""
        output = {}
        for activity in activities:
            if activity.get("activityType") != "version.publish":
                continue
            origin = (activity.get("activityData") or {}).get("origin") or {}
            if origin.get("id"):
                output[activity["activityId"]] = origin["id"]
        return output

    @staticmethod
    def _fill_published_versions(
        project_name: str,
        activity_models: list[Any],
        version_ids_by_activity_id: dict[str, str],
    ) -> None:
        """Fill current status and thumbnail of published versions."""
        if not version_ids_by_activity_id:
            return
        versions_by_id = {
            version["id"]: version
            for version in ayon_api.get_versions(
                project_name,
                version_ids=set(version_ids_by_activity_id.values()),
                fields={"id", "status", "thumbnailId"},
            )
        }
        for model in activity_models:
            if not isinstance(model, VersionPublishModel):
                continue
            version_id = version_ids_by_activity_id.get(model.activity_id)
            version = versions_by_id.get(version_id)
            if version is None:
                # The version was removed since
                continue
            model.status = version.get("status") or ""
            thumbnail_id = version.get("thumbnailId")
            if thumbnail_id:
                model.thumbnail_key = (
                    f"{project_name}/{version_id}/{thumbnail_id}"
                )

    def _get_users(self, project_name: str) -> list[User]:
        users = self._users_by_project.get(project_name)
        if users is None:
            users = [
                User(
                    name=user["name"],
                    # Activities are matched to users by 'short_name'
                    short_name=user["name"],
                    full_name=(
                        user.get("attrib", {}).get("fullName") or user["name"]
                    ),
                    email="",
                )
                for user in ayon_api.get_users(
                    project_name, fields={"name", "attrib.fullName"}
                )
            ]
            self._users_by_project[project_name] = users
        return users

    def _get_statuses(self, project_name: str) -> list[dict[str, Any]]:
        statuses = self._statuses_by_project.get(project_name)
        if statuses is None:
            project = ayon_api.get_project(project_name) or {}
            statuses = [
                {
                    "text": status["name"],
                    "short_text": status.get("shortName", ""),
                    "icon": status.get("icon", ""),
                    "color": status.get("color", ""),
                }
                for status in project.get("statuses", [])
            ]
            self._statuses_by_project[project_name] = statuses
        return statuses
