"""Temporal (time related) traits."""
from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING, Annotated, ClassVar, Optional, Union

from pydantic import Field, PlainSerializer

from .representation import Representation
from .trait import MissingTraitError, TraitBase

if TYPE_CHECKING:
    from decimal import Decimal


class GapPolicy(Enum):
    """Gap policy enumeration.

    This type defines how to handle gaps in sequence.

    Attributes:
        forbidden (int): Gaps are forbidden.
        missing (int): Gaps are interpreted as missing frames.
        hold (int): Gaps are interpreted as hold frames (last existing frames).
        black (int): Gaps are interpreted as black frames.
    """
    forbidden = auto()
    missing = auto()
    hold = auto()
    black = auto()

class FrameRanged(TraitBase):
    """Frame ranged trait model.

    Model representing a frame ranged trait.

    Sync with OpenAssetIO MediaCreation Traits. For compatibility with
    OpenAssetIO, we'll need to handle different names of attributes:

        * frame_start -> start_frame
        * frame_end -> end_frame
        ...

    Note: frames_per_second is a string to allow various precision
        formats. FPS is a floating point number, but it can be also
        represented as a fraction (e.g. "30000/1001") or as a decimal
        or even as irrational number. We need to support all these
        formats. To work with FPS, we'll need some helper function
        to convert FPS to Decimal from string.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        frame_start (int): Frame start.
        frame_end (int): Frame end.
        frame_in (int): Frame in.
        frame_out (int): Frame out.
        frames_per_second (str): Frames per second.
        step (int): Step.

    """
    name: ClassVar[str] = "FrameRanged"
    description: ClassVar[str] = "Frame Ranged Trait"
    id: ClassVar[str] = "ayon.time.FrameRanged.v1"
    frame_start: int = Field(
        ..., title="Start Frame")
    frame_end: int = Field(
        ..., title="Frame Start")
    frame_in: Optional[int] = Field(None, title="In Frame")
    frame_out: Optional[int] = Field(None, title="Out Frame")
    frames_per_second: str = Field(..., title="Frames Per Second")
    step: Optional[int] = Field(1, title="Step")


class Handles(TraitBase):
    """Handles trait model.

    Handles define the range of frames that are included or excluded
    from the sequence.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        inclusive (bool): Handles are inclusive.
        frame_start_handle (int): Frame start handle.
        frame_end_handle (int): Frame end handle.

    """
    name: ClassVar[str] = "Handles"
    description: ClassVar[str] = "Handles Trait"
    id: ClassVar[str] = "ayon.time.Handles.v1"
    inclusive: Optional[bool] = Field(
        False, title="Handles are inclusive")  # noqa: FBT003
    frame_start_handle: Optional[int] = Field(
        0, title="Frame Start Handle")
    frame_end_handle: Optional[int] = Field(
        0, title="Frame End Handle")

class Sequence(TraitBase):
    """Sequence trait model.

    This model represents a sequence trait. Based on the FrameRanged trait
    and Handles, adding support for gaps policy, frame padding and frame
    list specification. Regex is used to match frame numbers.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        gaps_policy (GapPolicy): Gaps policy - how to handle gaps in
            sequence.
        frame_padding (int): Frame padding.
        frame_regex (str): Frame regex - regular expression to match
            frame numbers.
        frame_list (str): Frame list specification of frames. This takes
            string like "1-10,20-30,40-50" etc.

    """
    name: ClassVar[str] = "Sequence"
    description: ClassVar[str] = "Sequence Trait Model"
    id: ClassVar[str] = "ayon.time.Sequence.v1"
    gaps_policy: GapPolicy = Field(
        GapPolicy.forbidden, title="Gaps Policy")
    frame_padding: int = Field(..., title="Frame Padding")
    frame_regex: str = Field(..., title="Frame Regex")
    frame_list: Optional[str] = Field(None, title="Frame List")

    def validate(self, representation: Representation) -> None:
        """Validate the trait."""
        if not super().validate(representation):
            return False

        # if there is FileLocations trait, run validation
        # on it as well
        try:
            from .content import FileLocations
            file_locs: FileLocations = representation.get_trait(
                FileLocations)
            file_locs.validate(representation)
        except MissingTraitError:
            pass

# Do we need one for drop and non-drop frame?
class SMPTETimecode(TraitBase):
    """SMPTE Timecode trait model."""
    name: ClassVar[str] = "Timecode"
    description: ClassVar[str] = "SMPTE Timecode Trait"
    id: ClassVar[str] = "ayon.time.SMPTETimecode.v1"
    timecode: str = Field(..., title="SMPTE Timecode HH:MM:SS:FF")


class Static(TraitBase):
    """Static time trait.

    Used to define static time (single frame).

    """
    name: ClassVar[str] = "Static"
    description: ClassVar[str] = "Static Time Trait"
    id: ClassVar[str] = "ayon.time.Static.v1"
