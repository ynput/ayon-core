"""Tests for the representation traits."""
from __future__ import annotations

import base64
import time
from pathlib import Path

import pyblish.api
import pytest
import pytest_ayon
from ayon_api.operations import (
    OperationsSession,
)
from ayon_core.pipeline.anatomy import Anatomy
from ayon_core.pipeline.traits import (
    FileLocation,
    FileLocations,
    FrameRanged,
    Image,
    MimeType,
    Persistent,
    PixelBased,
    Representation,
    Sequence,
    Transient,
)
from ayon_core.pipeline.version_start import get_versioning_start

# Tagged,
# TemplatePath,
from ayon_core.plugins.publish.integrate_traits import IntegrateTraits
from ayon_core.settings import get_project_settings

PNG_FILE_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABAQAAAAA3bvkkAAAACklEQVR4AWNgAAAAAgABc3UBGAAAAABJRU5ErkJggg=="  # noqa: E501
SEQUENCE_LENGTH = 10
CURRENT_TIME = time.time()


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
    dir_name = tmp_path_factory.mktemp("sequence")
    for i in range(SEQUENCE_LENGTH):
        frame = i + 1
        filename = dir_name / f"img.{frame:04d}.png"
        with open(filename, "wb") as f:
            f.write(base64.b64decode(PNG_FILE_B64))
        files.append(filename)
    return files

@pytest.fixture()
def mock_context(
        project: pytest_ayon.ProjectInfo,
        single_file: Path,
        sequence_files: list[Path]) -> pyblish.api.Context:
    """Return a mock instance.

    This is mocking pyblish context for testing. It is using real AYON project
    thanks to the ``project`` fixture.

    Args:
        project (object): The project info. It is `ProjectInfo` object
            returned by pytest fixture.
        single_file (Path): The path to a single image file.
        sequence_files (list[Path]): The paths to a sequence of image files.

    """
    anatomy = Anatomy(project.project_name)
    context = pyblish.api.Context()
    context.data["projectName"] = project.project_name
    context.data["hostName"] = "test_host"
    context.data["project_settings"] = get_project_settings(
        project.project_name)
    context.data["anatomy"] = anatomy
    context.data["time"] = CURRENT_TIME
    context.data["user"] = "test_user"
    context.data["machine"] = "test_machine"
    context.data["fps"] = 25

    instance = context.create_instance("mock_instance")
    instance.data["source"] = "test_source"
    instance.data["families"] = ["render"]
    instance.data["anatomyData"] = {
        "project": {
            "name": project.project_name,
            "code": project.project_code
        },
        "task": {
            "name": project.task.name,
            "type": "test"  # pytest-ayon doesn't return the task type yet
        },
        "folder": {
            "name": project.folder.name,
            "type": "test"  # pytest-ayon doesn't return the folder type yet
        },
        "product": {
            "name": project.product.name,
            "type": "test"  # pytest-ayon doesn't return the product type yet
        },

    }
    instance.data["folderEntity"] = project.folder_entity
    instance.data["productType"] = "test_product"
    instance.data["productName"] = project.product.name
    instance.data["anatomy"] = anatomy
    instance.data["comment"] = "test_comment"

    instance.data["integrate"] = True
    instance.data["farm"] = False

    parents = project.folder_entity["path"].lstrip("/").split("/")

    hierarchy = ""
    if parents:
        hierarchy = "/".join(parents)

    instance.data["hierarchy"] = hierarchy

    version_number = get_versioning_start(
        context.data["projectName"],
        instance.context.data["hostName"],
        task_name=project.task.name,
        task_type="test",
        product_type=instance.data["productType"],
        product_name=instance.data["productName"]
    )

    instance.data["version"] = version_number

    _file_size = len(base64.b64decode(PNG_FILE_B64))
    file_locations = [
        FileLocation(
            file_path=f,
            file_size=_file_size)
        for f in sequence_files]

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
            FrameRanged(
                frame_start=1,
                frame_end=SEQUENCE_LENGTH,
                frame_in=0,
                frame_out=SEQUENCE_LENGTH - 1,
                frames_per_second="25",
            ),
            Sequence(
                frame_padding=4,
                frame_regex=r"img\.(?P<index>(?P<padding>0*)\d{4})\.png$",
            ),
            FileLocations(
                file_paths=file_locations,
            ),
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


def test_prepare_product(
        project: pytest_ayon.ProjectInfo,
        mock_context: pyblish.api.Context) -> None:
    """Test prepare_product."""
    integrator = IntegrateTraits()
    op_session = OperationsSession()
    product = integrator.prepare_product(mock_context[0], op_session)

    assert product == {
        "attrib": {},
        "data": {
            "families": ["default", "render"],
            },
        "folderId": project.folder_entity["id"],
        "name": "renderMain",
        "productType": "test_product",
        "id": project.product_entity["id"],
        }

def test_prepare_version(
        project: pytest_ayon.ProjectInfo,
        mock_context: pyblish.api.Context) -> None:
    """Test prepare_version."""
    integrator = IntegrateTraits()
    op_session = OperationsSession()
    product = integrator.prepare_product(mock_context[0], op_session)
    version = integrator.prepare_version(
        mock_context[0], op_session , product)

    assert version == {
        "attrib": {
            "comment": "test_comment",
            "families": ["default", "render"],
            "fps": 25,
            "machine": "test_machine",
            "source": "test_source",
        },
        "data": {
            "author": "test_user",
            "time": CURRENT_TIME,
        },
        "id": project.version_entity["id"],
        "productId": project.product_entity["id"],
        "version": 1,
    }


def test_get_transfers_from_representation(
        mock_context: pyblish.api.Context) -> None:
    """Test get_transfers_from_representation.

    Todo: This test will benefit massively from a proper mocking of the
        context. We need to parametrize the test with different
        representations and test the output of the function.

    """
    integrator = IntegrateTraits()

    instance = mock_context[0]
    representations: list[Representation] = instance.data[
        "representations_with_traits"]
    transfers = integrator.get_transfers_from_representations(
        instance, representations)

    assert len(transfers) == 11
