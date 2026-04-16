"""Base class for reviewable providers."""

from abc import ABC, abstractmethod
from typing import Optional


class ReviewableProvider(ABC):
    """Abstract base class for reviewable/video providers.

    Providers can fetch reviewable videos from different sources.
    They are discovered via plugin system and executed in priority order.
    """

    # Priority order (lower = higher priority)
    priority = 100

    # Unique identifier for the provider
    identifier = None

    # Human-readable name
    label = None

    @abstractmethod
    def get_reviewable_path(
        self, project_name: str, version_ids: set, controller
    ) -> Optional[str]:
        """Get reviewable video path for given version(s).

        Args:
            project_name (str): Project name
            version_ids (set[str]): Set of version IDs to check
            controller: Loader controller instance

        Returns:
            Optional[str]: Path to video file if found, None otherwise
        """
        pass

    @abstractmethod
    def is_available(self, project_name: str, controller) -> bool:
        """Check if this provider is available/enabled for the project.

        Args:
            project_name (str): Project name
            controller: Loader controller instance

        Returns:
            bool: True if provider should be used
        """
        pass
