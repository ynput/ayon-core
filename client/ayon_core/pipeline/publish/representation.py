from dataclasses import dataclass, field, asdict
from typing import Any, Optional, Sequence, Union, overload


@dataclass
class Representation:
    name: str = ""
    ext: str = ""
    files: str | list[str] = field(default_factory=list)
    stagingDir: str = ""

    udim: Optional[list[str]] = None
    tags: Optional[list[str]] = field(default_factory=list)
    custom_tags: Optional[list[str]] = field(default_factory=list)
    colorspaceData: Optional[dict] = None
    resolutionWidth: Optional[int] = None
    resolutionHeight: Optional[int] = None
    source_resolution_width: Optional[int] = None
    source_resolution_height: Optional[int] = None
    fps: Optional[float] = None
    outputName: Optional[str] = None
    originalBasename: Optional[str] = None
    published_path: Optional[str] = None
    sequence_files: Optional[list[str]] = None
    stagingDir_persistent: Optional[bool] = None
    ffmpeg_cmd: Optional[list[str]] = None
    burnins: Optional[list[dict]] = None

    data: Optional[dict] = None

    def set_single_file(self, path: str) -> None:
        """Set single file for representation.

        Args:
            path (str): Path to the single file.
        """
        self.files = path

    @overload
    def set_sequence(self, files: Sequence[str]) -> None:
        ...

    def set_sequence(self, files: list[str]) -> None:
        """Set sequence of files for representation.

        Args:
            files (list[str]): List of file paths.
        """
        if len(files) == 1:
            self.set_single_file(files[0])
        else:
            self.files = list(files)
            self.sequence_files = list(files)

    def set_colorspace_data(self, colorspaceData: dict) -> None:
        if colorspaceData is None:
            self.colorspaceData = None
            return

        self.colorspaceData = colorspaceData

    def set_tags(self, tags: list[str]) -> None:
        if tags is None:
            self.tags = None
            return

        self.tags = tags

    def set_additional_data(self, data: dict) -> None:
        if data is None:
            self.data = None
            return

        self.data = data


def repre_get(repre: Union[Representation, dict], key: str) -> Any:
    """Get value from representation by key.

    Args:
        repre (Representation): Representation object.
        key (str): Key to get value from.

    Returns:
        Any: Value from representation.
    """
    if isinstance(repre, dict):
        return repre.get(key, None)

    return getattr(repre, key, None)


def repre_set(
        repre: Union[Representation, dict],
        key: str,
        value: Any) -> None:
    """Set value in representation by key.

    Args:
        repre (Representation): Representation object.
        key (str): Key to set value for.
        value (Any): Value to set.
    """
    if isinstance(repre, dict):
        repre[key] = value
    else:
        setattr(repre, key, value)


def repre_has(repre: Union[Representation, dict], key: str) -> bool:
    """Check if representation has key.

    Args:
        repre (Representation): Representation object.
        key (str): Key to check.

    Returns:
        bool: True if representation has key, False otherwise.
    """
    if isinstance(repre, dict):
        return key in repre

    return hasattr(repre, key)


def repre_copy(repre: Union[Representation, dict]) -> Union[Representation, dict]:
    """Copy representation.

    Args:
        repre (Representation): Representation object.

    Returns:
        Representation: Copied representation object.
    """
    if isinstance(repre, dict):
        return repre.copy()

    return Representation(
        name=repre.name,
        ext=repre.ext,
        files=repre.files,
        stagingDir=repre.stagingDir,
        udim=repre.udim,
        tags=repre.tags,
        custom_tags=repre.custom_tags,
        colorspaceData=repre.colorspaceData,
        resolutionWidth=repre.resolutionWidth,
        resolutionHeight=repre.resolutionHeight,
        fps=repre.fps,
        outputName=repre.outputName,
        originalBasename=repre.originalBasename,
        published_path=repre.published_path,
        sequence_files=repre.sequence_files,
        data=repre.data
    )


def repre_to_dict(repre: Union[Representation, dict]) -> dict:
    """Convert representation to dictionary.

    Args:
        repre (Representation): Representation object.

    Returns:
        dict: Representation as dictionary.
    """
    if isinstance(repre, dict):
        return repre

    return asdict(repre)
