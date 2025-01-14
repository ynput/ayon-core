import pytest
import logging
from pathlib import Path
from ayon_core.plugins.load.export_otio import get_image_info_metadata

logger = logging.getLogger('test_transcoding')


@pytest.mark.parametrize(
    "resources_path_factory, metadata, expected, test_id",
    [
        (
            Path(__file__).parent.parent
            / "resources"
            / "lib"
            / "transcoding"
            / "a01vfxd_sh010_plateP01_v002.1013.exr",
            ["timecode", "framerate"],
            {"timecode": "01:00:06:03", "framerate": 23.976023976023978},
            "test_01",
        ),
        (
            Path(__file__).parent.parent
            / "resources"
            / "lib"
            / "transcoding"
            / "a01vfxd_sh010_plateP01_v002.1013.exr",
            ["timecode", "width", "height", "duration"],
            {"timecode": "01:00:06:03", "width": 1920, "height": 1080},
            "test_02",
        ),
        (
            Path(__file__).parent.parent
            / "resources"
            / "lib"
            / "transcoding"
            / "a01vfxd_sh010_plateP01_v002.mov",
            ["width", "height", "duration"],
            {"width": 1920, "height": 1080, "duration": "0.041708"},
            "test_03",
        ),
    ],
)
def test_get_image_info_metadata_happy_path(
    resources_path_factory, metadata, expected, test_id
):
    path_to_file = resources_path_factory.as_posix()

    returned_data = get_image_info_metadata(path_to_file, metadata, logger)
    logger.info(f"Returned data: {returned_data}")

    assert returned_data == expected
