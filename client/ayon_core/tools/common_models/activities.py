"""Fetch entity activities (comments, publishes, status changes)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import ayon_api

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


class ActivitiesModel:
    """Model fetching activities of entities.

    Activities are always fetched so they are up to date. Project statuses
    and users needed to show them are available in 'ProjectsModel' and
    'UsersModel'.
    """

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
