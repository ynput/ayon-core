"""Tests for the representation traits."""
from __future__ import annotations

import base64
from typing import TYPE_CHECKING

import pyblish.api
import pytest
from ayon_core.pipeline.traits import (
    FileLocation,
    GapPolicy,
    Image,
    Persistent,
    PixelBased,
    Representation,
)

# Tagged,
# TemplatePath,
from ayon_core.plugins.publish.integrate_traits import IntegrateTraits
from pipeline.traits import MimeType, Sequence

if TYPE_CHECKING:
    from pathlib import Path

PNG_FILE_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABAQAAAAA3bvkkAAAACklEQVR4AWNgAAAAAgABc3UBGAAAAABJRU5ErkJggg=="  # noqa: E501
SEQUENCE_LENGTH = 10

@pytest.fixture(scope="session")
def single_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Return a temporary image file."""
    filename = tmp_path_factory.mktemp("single") / "img.png"
    with open(filename, "wb") as f:
        f.write(base64.b64decode(PNG_FILE_B64))
    return filename

def sequence_files(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    """Return a sequence of temporary image files."""
    files = []
    for i in range(SEQUENCE_LENGTH):
        filename = tmp_path_factory.mktemp("sequence") / f"img{i:04d}.png"
        with open(filename, "wb") as f:
            f.write(base64.b64decode(PNG_FILE_B64))
        files.append(filename)
    return files

@pytest.fixture()
def mock_context(
        single_file: Path,
        sequence_files: list[Path]) -> pyblish.api.Context:
    """Return a mock instance."""
    context = pyblish.api.Context()
    instance = context.create_instance("mock_instance")

    instance.data["integrate"] = True
    instance.data["farm"] = False

    instance.data["representations_with_traits"] = [
        Representation(name="test_single", traits=[
            Persistent(),
            FileLocation(
                file_path=single_file,
                file_size=len(base64.b64decode(PNG_FILE_B64))),
            Image(),
            MimeType(mime_type="image/png"),
        ]),
        Representation(name="test_sequence", traits=[
            Persistent(),
            Sequence(
                frame_start=1,
                frame_end=SEQUENCE_LENGTH,
                frame_padding=4,
                gaps_policy=GapPolicy.forbidden,
                frame_regex=r"img(\d{4}).png",
                step=1,
                frame_start_handle=0,
                frame_end_handle=0,
                frame_list=None
            ),
            FileLocation(
                file_path=sequence_files[0],
                file_size=len(base64.b64decode(PNG_FILE_B64))),
            Image(),
            PixelBased(
                display_window_width=1920,
                display_window_height=1080,
                pixel_aspect_ratio=1.0),
            MimeType(mime_type="image/png"),
        ]),
    ]

    return context

def test_get_template_name(mock_context: pyblish.api.Context) -> None:
    """Test get_template_name."""
    integrator = IntegrateTraits()
    template_name = integrator.get_template_name(
        mock_context["mock_instance"])

    assert template_name == "mock_instance"
