"""Reviewable provider system for loader tool.

Providers fetch reviewable videos from different sources:
- Representations (legacy/traditional approach)
- AYON Server Activities
- External trackers (Kitsu, Ftrack, etc.)
"""

from ayon_core.pipeline.plugin_discover import discover

from .base import ReviewableProvider


_REVIEWABLE_PROVIDERS_CACHE = None


def discover_reviewable_providers():
    """Discover all reviewable provider plugins.

    Returns:
        list[Type[ReviewableProvider]]: Discovered provider classes
            sorted by priority
    """
    global _REVIEWABLE_PROVIDERS_CACHE

    if _REVIEWABLE_PROVIDERS_CACHE is not None:
        return _REVIEWABLE_PROVIDERS_CACHE

    result = discover(ReviewableProvider)

    # Sort by priority (lower number = higher priority)
    providers = sorted(result.plugins, key=lambda p: p.priority)

    _REVIEWABLE_PROVIDERS_CACHE = providers
    return providers


def reset_reviewable_providers_cache():
    """Reset the cached providers (useful for development/testing)."""
    global _REVIEWABLE_PROVIDERS_CACHE
    _REVIEWABLE_PROVIDERS_CACHE = None


__all__ = [
    "ReviewableProvider",
    "discover_reviewable_providers",
    "reset_reviewable_providers_cache",
]
