from typing import Any

from .publish_plugins import DEFAULT_PUBLISH_VALUES


def _convert_imageio_configs_0_2_2(overrides):
    """Image IO settings had changed.

    0.2.2. is the latest version using the old way.
    """
    pass


def _convert_extract_intermediate_files_0_2_2(publish_overrides):
    """Extract intermediate files settings had changed.

    0.2.2. is the latest version using the old way.
    """
    pass


def _convert_publish_plugins(overrides):
    if "publish" not in overrides:
        return
    _convert_extract_intermediate_files_0_2_2(overrides["publish"])


def convert_settings_overrides(
    source_version: str,
    overrides: dict[str, Any],
) -> dict[str, Any]:
    _convert_imageio_configs_0_2_2(overrides)
    _convert_publish_plugins(overrides)
    return overrides
