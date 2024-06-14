import re
from typing import Any


def _get_viewer_config_from_string(input_string):
    """Convert string to display and viewer string

    Args:
        input_string (str): string with viewer

    Raises:
        IndexError: if more then one slash in input string
        IndexError: if missing closing bracket

    Returns:
        tuple[str]: display, viewer
    """
    display = None
    viewer = input_string
    # check if () or / or \ in name
    if "/" in viewer:
        split = viewer.split("/")

        # rise if more then one column
        if len(split) > 2:
            raise IndexError(
                "Viewer Input string is not correct. "
                f"More then two `/` slashes! {input_string}"
            )

        viewer = split[1]
        display = split[0]
    elif "(" in viewer:
        pattern = r"([\w\d\s\.\-]+).*[(](.*)[)]"
        result_ = re.findall(pattern, viewer)
        try:
            result_ = result_.pop()
            display = str(result_[1]).rstrip()
            viewer = str(result_[0]).rstrip()
        except IndexError as e:
            raise IndexError(
                "Viewer Input string is not correct. "
                f"Missing bracket! {input_string}"
            ) from e

    return (display, viewer)


def _convert_imageio_baking_0_2_3(overrides):
    if "baking" not in overrides:
        return

    baking_view_process = overrides["baking"].get("viewerProcess")

    if baking_view_process is None:
        return

    display, view = _get_viewer_config_from_string(baking_view_process)

    overrides["baking_target"] = {
        "enabled": True,
        "type": "display_view",
        "display_view": {
            "display": display,
            "view": view,
        },
    }


def _convert_viewers_0_2_3(overrides):
    if "viewer" not in overrides:
        return

    viewer = overrides["viewer"]

    if "viewerProcess" in viewer:
        viewer_process = viewer["viewerProcess"]
        display, view = _get_viewer_config_from_string(viewer_process)
        viewer.update({
            "display": display,
            "view": view,
        })
    if "output_transform" in viewer:
        output_transform = viewer["output_transform"]
        display, view = _get_viewer_config_from_string(output_transform)
        overrides["monitor"] = {
            "display": display,
            "view": view,
        }


def _convert_imageio_configs_0_2_3(overrides):
    """Image IO settings had changed.

    0.2.2. is the latest version using the old way.
    """
    if "imageio" not in overrides:
        return

    imageio_overrides = overrides["imageio"]

    _convert_imageio_baking_0_2_3(imageio_overrides)
    _convert_viewers_0_2_3(imageio_overrides)


def _convert_extract_intermediate_files_0_2_3(publish_overrides):
    """Extract intermediate files settings had changed.

    0.2.2. is the latest version using the old way.
    """
    # override can be either `display/view` or `view (display)`
    if "ExtractReviewIntermediates" in publish_overrides:
        extract_review_intermediates = publish_overrides[
            "ExtractReviewIntermediates"]

    for output in extract_review_intermediates.get("outputs", []):
        if viewer_process_override := output.get("viewer_process_override"):
            display, view = _get_viewer_config_from_string(
                viewer_process_override)

            output["colorspace_override"] = {
                "enabled": True,
                "type": "display_view",
                "display_view": {
                    "display": display,
                    "view": view,
                },
            }


def _convert_publish_plugins(overrides):
    if "publish" not in overrides:
        return
    _convert_extract_intermediate_files_0_2_3(overrides["publish"])


def convert_settings_overrides(
    source_version: str,
    overrides: dict[str, Any],
) -> dict[str, Any]:
    _convert_imageio_configs_0_2_3(overrides)
    _convert_publish_plugins(overrides)
    return overrides
