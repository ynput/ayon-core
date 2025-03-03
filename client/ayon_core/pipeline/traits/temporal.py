"""Temporal (time related) traits."""
from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass
from enum import Enum, auto
from re import Pattern
from typing import TYPE_CHECKING, ClassVar, Optional

import clique

from .trait import MissingTraitError, TraitBase, TraitValidationError

if TYPE_CHECKING:

    from .content import FileLocations
    from .representation import Representation


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


@dataclass
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
    persistent: ClassVar[bool] = True
    frame_start: int
    frame_end: int
    frame_in: Optional[int] = None
    frame_out: Optional[int] = None
    frames_per_second: str = None
    step: Optional[int] = None


@dataclass
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
    persistent: ClassVar[bool] = True
    inclusive: Optional[bool] = False
    frame_start_handle: Optional[int] = None
    frame_end_handle: Optional[int] = None


@dataclass
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
            frame numbers. Must include 'index' named group and 'padding'
            named group.
        frame_spec (str): Frame list specification of frames. This takes
            string like "1-10,20-30,40-50" etc.
    """

    name: ClassVar[str] = "Sequence"
    description: ClassVar[str] = "Sequence Trait Model"
    id: ClassVar[str] = "ayon.time.Sequence.v1"
    persistent: ClassVar[bool] = True
    frame_padding: int
    gaps_policy: Optional[GapPolicy] = GapPolicy.forbidden
    frame_regex: Optional[Pattern] = None
    frame_spec: Optional[str] = None

    @classmethod
    def validate_frame_regex(
        cls, v: Optional[Pattern]
    ) -> Optional[Pattern]:
        """Validate frame regex.

        Frame regex must have index and padding named groups.

        Returns:
            Optional[Pattern]: Compiled regex pattern.

        Raises:
            ValueError: If frame regex does not include 'index' and 'padding'

        """
        if v is None:
            return v
        if v and any(s not in v.pattern for s in ["?P<index>", "?P<padding>"]):
            msg = "Frame regex must include 'index' and `padding named groups"
            raise ValueError(msg)
        return v

    def validate_trait(self, representation: Representation) -> None:
        """Validate the trait."""
        super().validate_trait(representation)

        # if there is FileLocations trait, run validation
        # on it as well

        with contextlib.suppress(MissingTraitError):
            self._validate_file_locations(representation)

    def _validate_file_locations(self, representation: Representation) -> None:
        """Validate file locations trait.

        If along with the Sequence trait, there is a FileLocations trait,
        then we need to validate if the file locations match the frame
        list specification.

        Args:
            representation (Representation): Representation instance.

        """
        from .content import FileLocations
        file_locs: FileLocations = representation.get_trait(
            FileLocations)
        # validate if file locations on representation
        # matches the frame list (if any)
        # we need to extend the expected frames with Handles
        frame_start = None
        frame_end = None
        handles_frame_start = None
        handles_frame_end = None
        with contextlib.suppress(MissingTraitError):
            handles: Handles = representation.get_trait(Handles)
            # if handles are inclusive, they should be already
            # accounted in the FrameRaged frame spec
            if not handles.inclusive:
                handles_frame_start = handles.frame_start_handle
                handles_frame_end = handles.frame_end_handle
        with contextlib.suppress(MissingTraitError):
            frame_ranged: FrameRanged = representation.get_trait(
                FrameRanged)
            frame_start = frame_ranged.frame_start
            frame_end = frame_ranged.frame_end
        if self.frame_spec is not None:
            self.validate_frame_list(
                file_locs,
                frame_start,
                frame_end,
                handles_frame_start,
                handles_frame_end)

        self.validate_frame_padding(file_locs)

    def validate_frame_list(
            self,
            file_locations: FileLocations,
            frame_start: Optional[int] = None,
            frame_end: Optional[int] = None,
            handles_frame_start: Optional[int] = None,
            handles_frame_end: Optional[int] = None) -> None:
        """Validate frame list.

        This will take FileLocations trait and validate if the
        file locations match the frame list specification.

        For example, if frame list is "1-10,20-30,40-50", then
        the frame numbers in the file locations should match
        these frames.

        It will skip the validation if frame list is not provided.

        Args:
            file_locations (FileLocations): File locations trait.
            frame_start (Optional[int]): Frame start.
            frame_end (Optional[int]): Frame end.
            handles_frame_start (Optional[int]): Frame start handle.
            handles_frame_end (Optional[int]): Frame end handle.

        Raises:
            TraitValidationError: If frame list does not match
                the expected frames.

        """
        if self.frame_spec is None:
            return

        frames: list[int] = []
        if self.frame_regex:
            frames = self.get_frame_list(
                    file_locations, self.frame_regex)
        else:
            frames = self.get_frame_list(
                    file_locations)

        expected_frames = self.list_spec_to_frames(self.frame_spec)
        if frame_start is None or frame_end is None:
            if min(expected_frames) != frame_start:
                msg = (
                    "Frame start does not match the expected frame start. "
                    f"Expected: {frame_start}, Found: {min(expected_frames)}"
                )
                raise TraitValidationError(self.name, msg)

            if max(expected_frames) != frame_end:
                msg = (
                    "Frame end does not match the expected frame end. "
                    f"Expected: {frame_end}, Found: {max(expected_frames)}"
                )
                raise TraitValidationError(self.name, msg)

        # we need to extend the expected frames with Handles
        if handles_frame_start is not None:
            expected_frames.extend(
                range(
                    min(frames) - handles_frame_start, min(frames) + 1))

        if handles_frame_end is not None:
            expected_frames.extend(
                range(
                    max(frames), max(frames) + handles_frame_end + 1))

        if set(frames) != set(expected_frames):
            msg = (
                "Frame list does not match the expected frames. "
                f"Expected: {expected_frames}, Found: {frames}"
            )
            raise TraitValidationError(self.name, msg)

    def validate_frame_padding(
            self, file_locations: FileLocations) -> None:
        """Validate frame padding.

        This will take FileLocations trait and validate if the
        frame padding matches the expected frame padding.

        Args:
            file_locations (FileLocations): File locations trait.

        Raises:
            TraitValidationError: If frame padding does not match
                the expected frame padding.

        """
        expected_padding = self.get_frame_padding(file_locations)
        if self.frame_padding != expected_padding:
            msg = (
                "Frame padding does not match the expected frame padding. "
                f"Expected: {expected_padding}, Found: {self.frame_padding}"
            )
            raise TraitValidationError(self.name, msg)

    @staticmethod
    def list_spec_to_frames(list_spec: str) -> list[int]:
        """Convert list specification to frames.

        Returns:
            list[int]: List of frame numbers.

        Raises:
            ValueError: If invalid frame number in the list.

        """
        frames = []
        segments = list_spec.split(",")
        for segment in segments:
            ranges = segment.split("-")
            if len(ranges) == 1:
                if not ranges[0].isdigit():
                    msg = (
                        "Invalid frame number "
                        f"in the list: {ranges[0]}"
                    )
                    raise ValueError(msg)
                frames.append(int(ranges[0]))
                continue
            start, end = segment.split("-")
            frames.extend(range(int(start), int(end) + 1))
        return frames

    @staticmethod
    def _get_collection(
        file_locations: FileLocations,
        regex: Optional[Pattern] = None) -> clique.Collection:
        r"""Get collection from file locations.

        Args:
            file_locations (FileLocations): File locations trait.
            regex (Optional[Pattern]): Regular expression to match
                frame numbers. This is passed to ``clique.assemble()``.
                Default clique pattern is::

                    \.(?P<index>(?P<padding>0*)\d+)\.\D+\d?$

        Returns:
            clique.Collection: Collection instance.

        Raises:
            ValueError: If zero or multiple collections found.

        """
        patterns = [regex] if regex else None
        files: list[str] = [
            file.file_path.as_posix()
            for file in file_locations.file_paths
        ]
        src_collections, _ = clique.assemble(files, patterns=patterns)
        if len(src_collections) != 1:
            msg = (
                f"Zero or multiple collections found: {len(src_collections)} "
                "expected 1"
            )
            raise ValueError(msg)
        return src_collections[0]

    @staticmethod
    def get_frame_padding(file_locations: FileLocations) -> int:
        """Get frame padding.

        Returns:
            int: Frame padding.

        """
        src_collection = Sequence._get_collection(file_locations)
        return len(str(max(src_collection.indexes)))

    @staticmethod
    def get_frame_list(
            file_locations: FileLocations,
            regex: Optional[Pattern] = None,
        ) -> list[int]:
        r"""Get frame list.

        Args:
            file_locations (FileLocations): File locations trait.
            regex (Optional[Pattern]): Regular expression to match
                frame numbers. This is passed to ``clique.assemble()``.
                Default clique pattern is::

                    \.(?P<index>(?P<padding>0*)\d+)\.\D+\d?$

        Returns:
            list[int]: List of frame numbers.

        """
        src_collection = Sequence._get_collection(file_locations, regex)
        return list(src_collection.indexes)

    def get_frame_pattern(self) -> Pattern:
        """Get frame regex as pattern.

        If the regex is string, it will compile it to the pattern.

        Returns:
            Pattern: Compiled regex pattern.

        """
        if self.frame_regex:
            if isinstance(self.frame_regex, str):
                return re.compile(self.frame_regex)
            return self.frame_regex
        return re.compile(
            r"\.(?P<index>(?P<padding>0*)\d+)\.\D+\d?$")


# Do we need one for drop and non-drop frame?
@dataclass
class SMPTETimecode(TraitBase):
    """SMPTE Timecode trait model.

    Attributes:
        timecode (str): SMPTE Timecode HH:MM:SS:FF
    """

    name: ClassVar[str] = "Timecode"
    description: ClassVar[str] = "SMPTE Timecode Trait"
    id: ClassVar[str] = "ayon.time.SMPTETimecode.v1"
    persistent: ClassVar[bool] = True
    timecode: str


@dataclass
class Static(TraitBase):
    """Static time trait.

    Used to define static time (single frame).
    """

    name: ClassVar[str] = "Static"
    description: ClassVar[str] = "Static Time Trait"
    id: ClassVar[str] = "ayon.time.Static.v1"
    persistent: ClassVar[bool] = True
