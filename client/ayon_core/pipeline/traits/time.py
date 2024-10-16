"""Temporal (time related) traits."""
from enum import Enum, auto
from typing import ClassVar

from pydantic import Field

from .trait import TraitBase


class GapPolicy(Enum):
    """Gap policy enumeration.

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

class Clip(TraitBase):
    """Clip trait model.

    Model representing a clip trait.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        frame_start (int): Frame start.
        frame_end (int): Frame end.
        frame_start_handle (int): Frame start handle.
        frame_end_handle (int): Frame end handle.

    """
    name: ClassVar[str] = "Clip"
    description: ClassVar[str] = "Clip Trait"
    id: ClassVar[str] = "ayon.time.Clip.v1"
    frame_start: int = Field(..., title="Frame Start")
    frame_end: int = Field(..., title="Frame End")
    frame_start_handle: int = Field(..., title="Frame Start Handle")
    frame_end_handle: int = Field(..., title="Frame End Handle")

class Sequence(Clip):
    """Sequence trait model.

    This model represents a sequence trait. Based on the Clip trait,
    adding handling for steps, gaps policy and frame padding.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        step (int): Frame step.
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
    step: int = Field(..., title="Step")
    gaps_policy: GapPolicy = Field(
        GapPolicy.forbidden, title="Gaps Policy")
    frame_padding: int = Field(..., title="Frame Padding")
    frame_regex: str = Field(..., title="Frame Regex")
    frame_list: str = Field(..., title="Frame List")


# Do we need one for drop and non-drop frame?
class SMPTETimecode(TraitBase):
    """Timecode trait model."""
    name: ClassVar[str] = "Timecode"
    description: ClassVar[str] = "SMPTE Timecode Trait"
    id: ClassVar[str] = "ayon.time.SMPTETimecode.v1"
    timecode: str = Field(..., title="SMPTE Timecode HH:MM:SS:FF")
