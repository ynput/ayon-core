"""Tests for the representation traits."""
from __future__ import annotations

import base64
import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pyblish.api
import pytest
import ayon_core.plugins.publish.integrate_traits as integrate_traits_module

from ayon_core.lib.file_transaction import (
    FileTransaction,
)

from ayon_core.pipeline.anatomy import Anatomy
from ayon_core.pipeline.publish import (
    TemplateItem,
    get_template_name,
)
from ayon_core.pipeline.traits import (
    Bundle,
    FileLocation,
    FileLocations,
    FrameRanged,
    Image,
    MimeType,
    Persistent,
    PixelBased,
    Representation,
    Sequence,
    TemplatePath,
    Transient,

    TransferItem
)
from ayon_core.pipeline.traits.publishing import (
    get_transfers_from_file_locations_common_root,
    get_template_data_from_representation,
    get_transfers_from_representations,
    get_legacy_files_for_representation,
)
from ayon_core.pipeline.version_start import get_versioning_start

# Tagged,
# TemplatePath,
from ayon_core.plugins.publish.integrate_traits import (
    IntegrateTraits,
)

from ayon_core.settings import get_project_settings

from ayon_api.operations import (
    OperationsSession,
)

if TYPE_CHECKING:
    import pytest_ayon

PNG_FILE_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABAQAAAAA3bvkkAAAACklEQVR4AWNgAAAAAgABc3UBGAAAAABJRU5ErkJggg=="  # noqa: E501
SEQUENCE_LENGTH = 10
CURRENT_TIME = time.time()


@pytest.fixture(scope="session")
def single_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Return a temporary image file."""
    filename = tmp_path_factory.mktemp("single") / "img.png"
    filename.write_bytes(base64.b64decode(PNG_FILE_B64))
    return filename


@pytest.fixture(scope="session")
def sequence_files(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    """Return a sequence of temporary image files."""
    files = []
    dir_name = tmp_path_factory.mktemp("sequence")
    for i in range(SEQUENCE_LENGTH):
        frame = i + 1
        filename = dir_name / f"img.{frame:04d}.png"
        filename.write_bytes(base64.b64decode(PNG_FILE_B64))
        files.append(filename)
    return files


@pytest.fixture
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

    parents = project.folder_entity["path"].lstrip("/").split("/")
    hierarchy = "/".join(parents) if parents else ""

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
        "hierarchy": hierarchy,

    }
    instance.data["folderEntity"] = project.folder_entity
    instance.data["productType"] = "test_product"
    instance.data["productName"] = project.product.name
    instance.data["anatomy"] = anatomy
    instance.data["comment"] = "test_comment"

    instance.data["integrate"] = True
    instance.data["farm"] = False

    parents = project.folder_entity["path"].lstrip("/").split("/")

    hierarchy = "/".join(parents) if parents else ""
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

    file_size = len(base64.b64decode(PNG_FILE_B64))
    file_locations = [
        FileLocation(
            file_path=f,
            file_size=file_size)
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
                frame_regex=re.compile(
                    r"img\.(?P<index>(?P<padding>0*)\d{4})\.png$"),
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
        Representation(name="test_bundle", traits=[
            Persistent(),
            Bundle(
                items=[
                    [
                        FileLocation(
                            file_path=single_file,
                            file_size=len(base64.b64decode(PNG_FILE_B64))),
                        Image(),
                        MimeType(mime_type="image/png"),
                    ],
                    [
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
                            frame_regex=re.compile(
                                r"img\.(?P<index>(?P<padding>0*)\d{4})\.png$"),
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
                    ],
                ],
            ),
        ]),
    ]

    return context


@pytest.mark.server
def test_get_template_name(mock_context: pyblish.api.Context) -> None:
    """Test get_template_name.

    TODO (antirotor): this will always return "default" probably, if
        there are no studio overrides. To test this properly, we need
        to set up the studio overrides in the test environment.

    """
    template_name = get_template_name(
        mock_context[0])

    assert template_name == "default"


@pytest.mark.server
def test_get_template_data_from_representation(
        mock_context: pyblish.api.Context) -> None:
    """Test get_template_data_from_representation."""
    instance = mock_context[0]
    representations: list[Representation] = instance.data[
        "representations_with_traits"]

    for representation in representations:
        template_data = get_template_data_from_representation(
            representation, instance)

        assert template_data["project"]["name"] == instance.context.data[
            "projectName"]
        assert template_data["task"]["name"] == instance.data[
            "anatomyData"]["task"]["name"]
        assert template_data["product"]["name"] == instance.data[
            "productName"]
        if template_data.get("ext"):
            assert template_data["ext"] == "png"


class TestGetSize:
    @staticmethod
    def get_size(file_path: Path) -> int:
        """Get size of the file.

        Args:
            file_path (Path): File path.

        Returns:
            int: Size of the file.

        """
        return file_path.stat().st_size

    @pytest.mark.parametrize(
        "file_path, expected_size",
        [
            (Path("./test_file_1.txt"), 10),  # id: happy_path_small_file
            (Path("./test_file_2.txt"), 1024),  # id: happy_path_medium_file
            (Path("./test_file_3.txt"), 10485760)  # id: happy_path_large_file
        ],
        ids=["happy_path_small_file",
             "happy_path_medium_file",
             "happy_path_large_file"]
    )
    def test_get_size_happy_path(
            self, file_path: Path, expected_size: int, tmp_path: Path):
        # Arrange
        file_path = tmp_path / file_path
        file_path.write_bytes(b"\0" * expected_size)

        # Act
        size = self.get_size(file_path)

        # Assert
        assert size == expected_size

    @pytest.mark.parametrize(
        "file_path, expected_size",
        [
            (Path("./test_file_empty.txt"), 0)  # id: edge_case_empty_file
        ],
        ids=["edge_case_empty_file"]
    )
    def test_get_size_edge_cases(
            self, file_path: Path, expected_size: int, tmp_path: Path):
        # Arrange
        file_path = tmp_path / file_path
        file_path.touch()  # Create an empty file

        # Act
        size = self.get_size(file_path)

        # Assert
        assert size == expected_size

    @pytest.mark.parametrize(
        "file_path, expected_exception",
        [
            (
                    Path("./non_existent_file.txt"),
                    FileNotFoundError
            ),  # id: error_file_not_found
            (123, TypeError)  # id: error_invalid_input_type
        ],
        ids=["error_file_not_found", "error_invalid_input_type"]
    )
    def test_get_size_error_cases(
            self, file_path, expected_exception, tmp_path):

        # Act & Assert
        with pytest.raises(expected_exception):
            file_path = tmp_path / file_path
            self.get_size(file_path)


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


@pytest.mark.server
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


@pytest.mark.server
def test_prepare_version(
        project: pytest_ayon.ProjectInfo,
        mock_context: pyblish.api.Context) -> None:
    """Test prepare_version."""
    integrator = IntegrateTraits()
    op_session = OperationsSession()
    product = integrator.prepare_product(mock_context[0], op_session)
    version = integrator.prepare_version(
        mock_context[0], op_session, product)

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


@pytest.mark.server
def test_get_transfers_from_representation(
        mock_context: pyblish.api.Context) -> None:
    """Test get_transfers_from_representation.

    This tests getting actual transfers from the representations and
    also the legacy files.

    Todo: This test will benefit massively from a proper mocking of the
        context. We need to parametrize the test with different
        representations and test the output of the function.

    """
    instance = mock_context[0]
    anatomy = instance.context.data["anatomy"]
    template_item = anatomy.get_template_item("hero", "default")
    representations: list[Representation] = instance.data[
        "representations_with_traits"]
    transfers = get_transfers_from_representations(
        instance, template_item, representations)

    assert len(representations) == 3
    assert len(transfers) == 22

    for transfer in transfers:
        assert transfer.checksum == TransferItem.get_checksum(
            transfer.source)

    file_transactions = FileTransaction(
        # Enforce unique transfers
        allow_queue_replacements=False)

    for transfer in transfers:
        file_transactions.add(
            transfer.source.as_posix(),
            transfer.destination.as_posix(),
            mode=FileTransaction.MODE_COPY,
        )

    file_transactions.process()

    for representation in representations:
        _ = get_legacy_files_for_representation(  # noqa: SLF001
            transfers, representation, anatomy=instance.data["anatomy"])


def test_get_transfers_from_representation_preserves_hierarchy(
        tmp_path: Path) -> None:
    """FileLocations without Sequence/UDIM should keep relative hierarchy."""
    common_root = tmp_path / "textures"
    destination_root = tmp_path / "publish"
    file_paths = [
        common_root / "diffuse" / "beauty.png",
        common_root / "masks" / "crypto" / "object.png",
    ]
    for file_path in file_paths:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(base64.b64decode(PNG_FILE_B64))

    representation = Representation(name="test_hierarchy", traits=[
        Persistent(),
        FileLocations(file_paths=[
            FileLocation(
                file_path=file_path,
                file_size=file_path.stat().st_size,
            )
            for file_path in file_paths
        ]),
        Image(),
        MimeType(mime_type="image/png"),
    ])

    class _DummyTemplateResult(str):
        def __new__(cls, value: str):
            obj = cast(_DummyTemplateResult, super().__new__(cls, value))
            obj.used_values = {}
            return obj

    class _DummyPathTemplate:
        def __init__(self, value: str):
            self.value = value

        def format_strict(self, _data: dict) -> _DummyTemplateResult:
            return _DummyTemplateResult(self.value)

    template_item = TemplateItem(
        anatomy=cast(Anatomy, object()),
        template="{root}/publish/placeholder.png",
        template_data={},
        template_object=cast(Any, {
            "path": _DummyPathTemplate(
                (destination_root / "placeholder.png").as_posix()
            )
        }),
    )
    transfers: list[TransferItem] = []

    get_transfers_from_file_locations_common_root(
        representation,
        template_item,
        transfers,
    )

    assert len(transfers) == len(file_paths)

    relative_destinations = {
        transfer.destination.relative_to(destination_root)
        for transfer in transfers
    }
    expected_relative_destinations = {
        file_path.relative_to(common_root)
        for file_path in file_paths
    }
    assert relative_destinations == expected_relative_destinations

    template_path = representation.get_trait(TemplatePath)
    assert template_path.template == template_item.template


def test_integrate_traits_process_passes_template_object(
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path) -> None:
    """Process should pass a resolved template object to transfer builder."""
    expected_template = {
        "path": "dummy/path/{representation}.{ext}",
    }

    class _DummyAnatomy:
        def get_template_item(self, category: str, template_name: str):
            assert category == "publish"
            assert template_name == "default"
            return expected_template

    context = pyblish.api.Context()
    context.data["projectName"] = "test_project"
    context.data["anatomy"] = _DummyAnatomy()
    instance = context.create_instance("mock_instance")
    instance.data["integrate"] = True
    instance.data["farm"] = False

    source = tmp_path / "source" / "image.png"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(base64.b64decode(PNG_FILE_B64))

    file_location = FileLocation(
        file_path=source,
        file_size=source.stat().st_size,
    )
    representation = Representation(name="test_single", traits=[
        Persistent(),
        file_location,
        Image(),
        MimeType(mime_type="image/png"),
    ])

    class _DummyOperationsSession:
        def __init__(self):
            self.created = []
            self.committed = False

        def create_entity(self, project_name, entity_type, data):
            self.created.append((project_name, entity_type, data))

        def to_data(self):
            return {}

        def commit(self):
            self.committed = True

    class _DummyFileTransaction:
        MODE_COPY = "copy"

        def __init__(self, *args, **kwargs):
            self.transferred = []

        def add(self, source_path, destination_path, mode):
            self.transferred.append((source_path, destination_path, mode))

        def process(self):
            return None

    captured = {}

    monkeypatch.setattr(
        integrate_traits_module,
        "has_trait_representations",
        lambda _instance: True,
    )
    monkeypatch.setattr(
        integrate_traits_module,
        "get_trait_representations",
        lambda _instance: [representation],
    )
    monkeypatch.setattr(
        integrate_traits_module,
        "set_trait_representations",
        lambda _instance, _representations: None,
    )
    monkeypatch.setattr(
        integrate_traits_module.IntegrateTraits,
        "filter_lifecycle",
        staticmethod(lambda representations: representations),
    )
    monkeypatch.setattr(
        integrate_traits_module.IntegrateTraits,
        "prepare_product",
        lambda self, _instance, _op_session: {"id": "product-id"},
    )
    monkeypatch.setattr(
        integrate_traits_module.IntegrateTraits,
        "prepare_version",
        lambda self, _instance, _op_session, _product: {"id": "version-id"},
    )
    monkeypatch.setattr(
        integrate_traits_module,
        "get_template_name",
        lambda _instance: "default",
    )

    def _mock_get_transfers(instance_arg, template_arg, representations_arg):
        captured["instance"] = instance_arg
        captured["template"] = template_arg
        captured["representations"] = representations_arg
        return [TransferItem(
            source=source,
            destination=tmp_path / "publish" / "image.png",
            size=source.stat().st_size,
            checksum=TransferItem.get_checksum(source),
            template="dummy/path/{representation}.{ext}",
            template_data={},
            representation=representation,
            related_trait=file_location,
        )]

    monkeypatch.setattr(
        integrate_traits_module,
        "get_transfers_from_representations",
        _mock_get_transfers,
    )
    monkeypatch.setattr(
        integrate_traits_module,
        "FileTransaction",
        _DummyFileTransaction,
    )
    monkeypatch.setattr(
        integrate_traits_module,
        "OperationsSession",
        _DummyOperationsSession,
    )
    monkeypatch.setattr(
        integrate_traits_module,
        "new_representation_entity",
        lambda *args, **kwargs: {},
    )
    monkeypatch.setattr(
        integrate_traits_module,
        "get_template_data_from_representation",
        lambda _representation, _instance: {},
    )
    monkeypatch.setattr(
        integrate_traits_module.IntegrateTraits,
        "_get_legacy_files_for_representation",
        lambda self, _transfers, _representation, anatomy: [],
    )

    plugin = IntegrateTraits()
    plugin.log = logging.getLogger("test_integrate_traits")

    plugin.process(instance)

    assert captured["instance"] is instance
    assert captured["template"] is expected_template
    assert captured["representations"] == [representation]
    assert instance.data[
        "publishedRepresentationsWithTraits"
    ] == [representation]
