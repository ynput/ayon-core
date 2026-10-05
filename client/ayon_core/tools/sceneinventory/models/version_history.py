"""Version history of products loaded in the scene."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterable

import ayon_api

from ayon_core.lib import Logger
from ayon_core.ui.image_cache import ImageCache

if TYPE_CHECKING:
    from ayon_core.tools.sceneinventory.control import (
        SceneInventoryController,
    )

VERSION_FIELDS = {
    "id",
    "version",
    "productId",
    "author",
    "createdAt",
    "status",
    "attrib.comment",
    "thumbnailId",
}


@dataclass
class VersionHistoryItem:
    """Single version in the history of a product.

    Attributes:
        version_id: Version id.
        product_id: Id of the product the version belongs to.
        version: Version number, negative for a hero version.
        author_name: Username of the user who published the version.
        author: Full name of the user, or the username if the full name
            is not known.
        created_at: Publish date in ISO format.
        comment: Comment filled on publish (version attribute 'comment').
        status: Status name.
        is_latest: It is the highest version of the product.
        thumbnail_id: Id of the version thumbnail, if it has any.
    """

    version_id: str
    product_id: str
    version: int
    author_name: str = ""
    author: str = ""
    created_at: str = ""
    comment: str = ""
    status: str = ""
    is_latest: bool = False
    thumbnail_id: str = ""

    @property
    def is_hero(self) -> bool:
        """Version is a hero version."""
        return self.version < 0


@dataclass
class VersionHistoryContext:
    """Product of selected containers with its versions used in the scene.

    Attributes:
        project_name: Project the product is in.
        product_id: Product id.
        product_name: Product name.
        folder_path: Path of the folder the product is in.
        loaded_version_ids: Ids of versions loaded by the containers.
    """

    project_name: str
    product_id: str
    product_name: str = ""
    folder_path: str = ""
    loaded_version_ids: set[str] = field(default_factory=set)


class VersionHistoryModel:
    """Model providing version history of products used by containers.

    Args:
        controller: Scene inventory controller.
    """

    def __init__(self, controller: SceneInventoryController) -> None:
        self._controller = controller
        self._items_by_product: dict[
            tuple[str, str], list[VersionHistoryItem]
        ] = {}
        self._user_names_by_project: dict[str, dict[str, str]] = {}
        self._log = Logger.get_logger("VersionHistoryModel")

    def reset(self) -> None:
        """Clear cached data."""
        self._items_by_product = {}
        self._user_names_by_project = {}

    def get_contexts(
        self, item_ids: Iterable[str]
    ) -> list[VersionHistoryContext]:
        """Find products used by containers.

        Containers of the same product are merged into one context, so
        more loaded versions of one product can be compared.

        Args:
            item_ids: Ids of container items.

        Returns:
            Contexts of valid containers, in order of the item ids.
        """
        container_items = [
            container_item
            for container_item in (
                self._controller.get_container_items_by_id(item_ids).values()
            )
            if container_item is not None
        ]
        repre_ids_by_project: dict[str, set[str]] = {}
        for container_item in container_items:
            repre_ids_by_project.setdefault(
                container_item.project_name, set()
            ).add(container_item.representation_id)

        contexts: dict[tuple[str, str], VersionHistoryContext] = {}
        for project_name, repre_ids in repre_ids_by_project.items():
            repre_info_by_id = (
                self._controller.get_representation_info_items(
                    project_name, repre_ids
                )
            )
            for repre_info in repre_info_by_id.values():
                if not repre_info.is_valid:
                    continue
                context = contexts.setdefault(
                    (project_name, repre_info.product_id),
                    VersionHistoryContext(
                        project_name=project_name,
                        product_id=repre_info.product_id,
                        product_name=repre_info.product_name or "",
                        folder_path=repre_info.folder_path or "",
                    ),
                )
                context.loaded_version_ids.add(repre_info.version_id)
        return list(contexts.values())

    def get_items(
        self, project_name: str, product_id: str
    ) -> list[VersionHistoryItem]:
        """Get versions of a product, from the newest to the oldest.

        A hero version is listed first. Can be called outside of the main
        thread.

        Args:
            project_name: Project name.
            product_id: Product id.

        Returns:
            Versions of the product.
        """
        cache_key = (project_name, product_id)
        items = self._items_by_product.get(cache_key)
        if items is not None:
            return list(items)

        version_entities = list(
            ayon_api.get_versions(
                project_name,
                product_ids={product_id},
                fields=VERSION_FIELDS,
            )
        )
        user_names = self._get_user_names(project_name)
        last_version = max(
            (
                entity["version"]
                for entity in version_entities
                if entity["version"] >= 0
            ),
            default=None,
        )
        items = [
            self._create_item(entity, user_names, last_version)
            for entity in version_entities
        ]
        items.sort(
            key=lambda item: (item.is_hero, abs(item.version)), reverse=True
        )
        self._items_by_product[cache_key] = items
        return list(items)

    @staticmethod
    def _create_item(
        entity: dict[str, Any],
        user_names: dict[str, str],
        last_version: int | None,
    ) -> VersionHistoryItem:
        author = entity.get("author") or ""
        return VersionHistoryItem(
            version_id=entity["id"],
            product_id=entity["productId"],
            version=entity["version"],
            author_name=author,
            author=user_names.get(author) or author,
            created_at=entity.get("createdAt") or "",
            comment=(entity.get("attrib") or {}).get("comment") or "",
            status=entity.get("status") or "",
            is_latest=entity["version"] == last_version,
            thumbnail_id=entity.get("thumbnailId") or "",
        )

    def get_thumbnail_path(
        self, project_name: str, version_id: str, thumbnail_id: str
    ) -> str:
        """Get path to a file with the thumbnail of a version.

        The image is downloaded on the first request, the cache is shared
        with the Browser tool. Can be called outside of the main thread.

        Args:
            project_name: Project name.
            version_id: Version id.
            thumbnail_id: Id of the version thumbnail.

        Returns:
            Path to the image, or an empty string if there is none.
        """
        if not project_name or not version_id or not thumbnail_id:
            return ""

        def _fetch() -> str:
            content = ayon_api.get_version_thumbnail(
                project_name, version_id, thumbnail_id
            )
            if not content.is_valid:
                return ""
            ext = ".png"
            if content.content_type and "jpeg" in content.content_type:
                ext = ".jpg"
            with tempfile.NamedTemporaryFile(
                suffix=ext, delete=False
            ) as stream:
                stream.write(content.content)
                return stream.name

        try:
            return ImageCache.get_instance().get(
                f"{project_name}/{version_id}/{thumbnail_id}", _fetch
            )
        except Exception:
            self._log.debug("Failed to fetch thumbnail", exc_info=True)
            return ""

    def _get_user_names(self, project_name: str) -> dict[str, str]:
        """Full names of project users by username."""
        user_names = self._user_names_by_project.get(project_name)
        if user_names is not None:
            return user_names
        try:
            user_names = {
                user["name"]: (user.get("attrib") or {}).get("fullName") or ""
                for user in ayon_api.get_users(
                    project_name, fields={"name", "attrib.fullName"}
                )
            }
        except Exception:
            # Usernames are good enough, e.g. with limited permissions
            self._log.debug("Failed to fetch users", exc_info=True)
            user_names = {}
        self._user_names_by_project[project_name] = user_names
        return user_names
