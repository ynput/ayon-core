"""AYON server activity-based reviewable provider."""

from ayon_core.settings import get_project_settings

from .base import ReviewableProvider


class ActivityProvider(ReviewableProvider):
    """Provider for AYON server activity-based reviewables.

    This provider fetches reviewable videos that are uploaded
    to the AYON server as activities (e.g., review submissions).

    Note: This is a placeholder for future implementation when
    AYON server API supports activity-based reviewables.
    """

    priority = 10  # High priority (try first)
    identifier = "activity"
    label = "Server Activities"

    def get_reviewable_path(self, project_name, version_ids, controller):
        """Get video from AYON server activities.

        Args:
            project_name (str): Project name
            version_ids (set[str]): Version IDs to check
            controller: Loader controller instance

        Returns:
            Optional[str]: Path to video file if found, None otherwise
        """
        # TODO: Implement when AYON API supports activity-based reviewables
        # This would query activities for versions and get media URLs

        # Pseudo-code for future implementation:
        # try:
        #     import ayon_api
        #
        #     for version_id in version_ids:
        #         activities = ayon_api.get_activities(
        #             project_name,
        #             version_id=version_id,
        #             activity_type="reviewable"
        #         )
        #         for activity in activities:
        #             media_url = activity.get("data", {}).get("media_url")
        #             if media_url:
        #                 # Download or get local cache path
        #                 return self._get_or_download_media(media_url)
        # except Exception as e:
        #     controller.log.debug(f"Failed to get activity reviewable: {e}")

        return None

    def is_available(self, project_name, controller):
        """Check if enabled in project settings.

        Args:
            project_name (str): Project name
            controller: Loader controller instance

        Returns:
            bool: True if this provider should be used
        """
        try:
            settings = get_project_settings(project_name)
            return (
                settings.get("core", {})
                .get("tools", {})
                .get("loader", {})
                .get("reviewable_providers", {})
                .get("use_activities", False)
            )
        except Exception:
            return False
