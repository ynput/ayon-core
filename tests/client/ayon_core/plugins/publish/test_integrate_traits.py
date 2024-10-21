"""Tests for the representation traits."""
from __future__ import annotations

import base64
from pathlib import Path

import pyblish.api
import pytest
from ayon_core.pipeline.traits import (
    FileLocation,
    Image,
    MimeType,
    Persistent,
    PixelBased,
    Representation,
    Sequence,
    Transient,
)

# Tagged,
# TemplatePath,
from ayon_core.plugins.publish.integrate_traits import IntegrateTraits
from ayon_core.settings import get_project_settings

PNG_FILE_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABAQAAAAA3bvkkAAAACklEQVR4AWNgAAAAAgABc3UBGAAAAABJRU5ErkJggg=="  # noqa: E501
SEQUENCE_LENGTH = 10

@pytest.fixture(scope="session")
def single_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Return a temporary image file."""
    filename = tmp_path_factory.mktemp("single") / "img.png"
    with open(filename, "wb") as f:
        f.write(base64.b64decode(PNG_FILE_B64))
    return filename

@pytest.fixture(scope="session")
def sequence_files(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    """Return a sequence of temporary image files."""
    files = []
    for i in range(SEQUENCE_LENGTH):
        filename = tmp_path_factory.mktemp("sequence") / f"img.{i:04d}.png"
        with open(filename, "wb") as f:
            f.write(base64.b64decode(PNG_FILE_B64))
        files.append(filename)
    return files

@pytest.fixture()
def mock_context(
        project: object,
        single_file: Path,
        sequence_files: list[Path]) -> pyblish.api.Context:
    """Return a mock instance.

    This is mocking pyblish context for testing. It is using real AYON project
    thanks to the ``project`` fixture.

    This returns following data::

        project_name: str
        project_code: str
        project_root_folders: dict[str, str]
        folder: IdNamePair
        task: IdNamePair
        product: IdNamePair
        version: IdNamePair
        representations: List[IdNamePair]
        links: List[str]

    Args:
        project (object): The project info. It is `ProjectInfo` object
            returned by pytest fixture.
        single_file (Path): The path to a single image file.
        sequence_files (list[Path]): The paths to a sequence of image files.

    """
    context = pyblish.api.Context()
    context.data["projectName"] = project.project_name
    context.data["hostName"] = "test_host"
    context.data["project_settings"] = get_project_settings(
        project.project_name)

    instance = context.create_instance("mock_instance")
    instance.data["anatomyData"] = {
        "project": project.project_name,
        "task": {
            "name": project.task.name,
            "type": "test"  # pytest-ayon doesn't return the task type yet
        }
    }
    instance.data["productType"] = "test_product"

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
                frame_regex=r"^img\.(\d{4})\.png$",
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
    """Test get_template_name.

    TODO (antirotor): this will always return "default" probably, if
        there are no studio overrides. To test this properly, we need
        to set up the studio overrides in the test environment.

    """
    integrator = IntegrateTraits()
    template_name = integrator.get_template_name(
        mock_context[0])

    assert template_name == "default"

def test_filter_lifecycle() -> None:
    """Test filter_lifecycle."""
    integrator = IntegrateTraits()
    persistent_representation = Representation(
        name="test",
        traits=[
                Persistent(),
                FileLocation(
                    file_path=Path("test"),
                    file_size=1234),
                Image(),
                MimeType(mime_type="image/png"),
            ])
    transient_representation = Representation(
        name="test",
        traits=[
                Transient(),
                Image(),
                MimeType(mime_type="image/png"),
            ])
    filtered = integrator.filter_lifecycle(
        [persistent_representation, transient_representation])

    assert len(filtered) == 1
    assert filtered[0] == persistent_representation
