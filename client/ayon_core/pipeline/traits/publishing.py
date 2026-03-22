"""Publishing related methods for traits."""
from __future__ import annotations

import contextlib
import copy
import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from ayon_core.pipeline.publish import (
    PublishError,
    get_template_name,
    TemplateItem,
)
from ayon_core.pipeline.traits import (
    FileLocation,
    FileLocations,
    ColorManaged,
    PixelBased,
    Bundle,
    Representation,
    Sequence,
    TemplatePath,
    Transient,
    FrameRanged,
    MissingTraitError,
    TraitValidationError,
    UDIM,
    Variant,
)
import pyblish.api

if TYPE_CHECKING:
    from ayon_core.pipeline import Anatomy
    from ayon_core.pipeline.anatomy.templates import (
        AnatomyStringTemplate,
        TemplateItem as AnatomyTemplateItem,
    )


class TransferItem:
    """Represents a single transfer item.

    Source file path, destination file path, template that was used to
    construct the destination path, template data that was used in the
    template, size of the file, checksum of the file.

    Attributes:
        source (Path): Source file path.
        destination (Path): Destination file path.
        size (int): Size of the file.
        checksum (str): Checksum of the file.
        template (str): Template path.
        template_data (dict[str, Any]): Template data.
        representation (Representation): Reference to representation
        related_trait (FileLocation): Reference to the trait that this
            transfer is related to. This is used to update the trait with
            the new file path after the transfer is done.

    """
    source: Path
    destination: Path
    size: int
    checksum: str
    template: str
    template_data: dict[str, Any]
    representation: Representation
    related_trait: FileLocation

    def __init__(self,
        source: Path,
        destination: Path,
        size: int,
        checksum: str,
        template: str,
        template_data: dict[str, Any],
        representation: Representation,
        related_trait: FileLocation):

        self.source = source
        self.destination = destination
        self.size = size
        self.checksum = checksum
        self.template = template
        self.template_data = template_data
        self.representation = representation
        self.related_trait = related_trait

    @staticmethod
    def get_size(file_path: Path) -> int:
        """Get the size of the file.

        Args:
            file_path (Path): File path.

        Returns:
            int: Size of the file.

        """
        return file_path.stat().st_size

    @staticmethod
    def get_checksum(file_path: Path) -> str:
        """Get checksum of the file.

        Args:
            file_path (Path): File path.

        Returns:
            str: Checksum of the file.

        """
        return hashlib.sha256(
            file_path.read_bytes()
        ).hexdigest()


def get_template_item_from_template_str():
    ...


def get_publish_template_object(
        instance: pyblish.api.Instance,
        category_name: str = "publish",
        template_name: Optional[str] = None,
) -> "AnatomyTemplateItem":
    """Return anatomy template object to use for integration.

    Note: What is the actual type of the object?

    Args:
        instance (pyblish.api.Instance): Instance to process.
        category_name (str): Category name of the template to use.
            Defaults to "publish".
        template_name (str, optional): Template name to use.
            If not provided, it will

    Returns:
        AnatomyTemplateItem: Anatomy template object

    """
    # Anatomy data is pre-filled by Collectors
    if not template_name:
        template_name = get_template_name(instance)
    anatomy: Anatomy = instance.context.data["anatomy"]
    return anatomy.get_template_item(
        category_name=category_name,
        template_name=template_name
    )


def get_transfers_from_sequence(
        representation: Representation,
        template_item: TemplateItem,
        transfers: list[TransferItem]
) -> None:
    """Get transfers from Sequence trait.

    Args:
        representation (Representation): Representation to process.
        template_item (TemplateItem): Template item.
        transfers (list): List of transfers.

    Mutates:
        transfers (list): List of transfers.
        template_item (TemplateItem): Template item.

    """
    sequence: Sequence = representation.get_trait(Sequence)
    path_template_object = template_item.template_object["path"]

    # get the padding from the sequence if the padding on the
    # template is higher, us the one from the template
    dst_padding = representation.get_trait(
        Sequence).frame_padding
    frames: list[int] = sequence.get_frame_list(
        representation.get_trait(FileLocations),
        regex=sequence.frame_regex)
    template_padding = template_item.anatomy.templates_obj.frame_padding
    dst_padding = max(template_padding, dst_padding)

    # Go through all frames in the sequence and
    # find their corresponding file locations, then
    # format their template and add them to transfers.
    for frame in frames:
        file_loc: FileLocation = representation.get_trait(
            FileLocations).get_file_location_for_frame(
            frame, sequence)

        template_item.template_data["frame"] = frame
        template_item.template_data["ext"] = (
            file_loc.file_path.suffix.lstrip("."))
        template_filled = path_template_object.format_strict(
            template_item.template_data
        )

        # add used values to the template data
        used_values: dict = template_filled.used_values
        template_item.template_data.update(used_values)

        transfers.append(
            TransferItem(
                source=file_loc.file_path,
                destination=Path(template_filled),
                size=file_loc.file_size or TransferItem.get_size(
                    file_loc.file_path),
                checksum=file_loc.file_hash or TransferItem.get_checksum(
                    file_loc.file_path),
                template=template_item.template,
                template_data=template_item.template_data,
                representation=representation,
                related_trait=file_loc
            )
        )

    # add template path and the data to resolve it
    if not representation.contains_trait(TemplatePath):
        representation.add_trait(TemplatePath(
            template=template_item.template,
            data=template_item.template_data
        ))


def get_transfers_from_udim(
        representation: Representation,
        template_item: TemplateItem,
        transfers: list[TransferItem]
) -> None:
    """Get transfers from UDIM trait.

    Args:
        representation (Representation): Representation to process.
        template_item (TemplateItem): Template item.
        transfers (list): List of transfers.

    Mutates:
        transfers (list): List of transfers.
        template_item (TemplateItem): Template item.

    """
    udim: UDIM = representation.get_trait(UDIM)
    path_template_object: "AnatomyStringTemplate" = (
        template_item.template_object["path"]
    )
    for file_loc in representation.get_trait(
            FileLocations).file_paths:
        template_item.template_data["udim"] = (
            udim.get_udim_from_file_location(file_loc)
        )

        template_filled = path_template_object.format_strict(
            template_item.template_data
        )

        # add used values to the template data
        used_values: dict = template_filled.used_values
        template_item.template_data.update(used_values)

        transfers.append(
            TransferItem(
                source=file_loc.file_path,
                destination=Path(template_filled),
                size=file_loc.file_size or TransferItem.get_size(
                    file_loc.file_path),
                checksum=file_loc.file_hash or TransferItem.get_checksum(
                    file_loc.file_path),
                template=template_item.template,
                template_data=template_item.template_data,
                representation=representation,
                related_trait=file_loc
            )
        )
    # add template path and the data to resolve it
    representation.add_trait(TemplatePath(
        template=template_item.template,
        data=template_item.template_data
    ))


def get_transfers_from_file_locations(
        representation: Representation,
        template_item: TemplateItem,
        transfers: list[TransferItem]) -> None:
    """Get transfers from FileLocations trait.

    Args:
        representation (Representation): Representation to process.
        template_item (TemplateItem): Template item.
        transfers (list): List of transfers.

    Mutates:
        transfers (list): List of transfers.
        template_item (TemplateItem): Template item.

    """
    if representation.contains_trait(Sequence):
        get_transfers_from_sequence(
            representation, template_item, transfers
        )

    elif representation.contains_trait(UDIM) and \
            not representation.contains_trait(Sequence):
        # handle UDIM not in sequence
        get_transfers_from_udim(
            representation, template_item, transfers
        )

    else:
        get_transfers_from_file_locations_common_root(
            representation, template_item, transfers
        )


def get_transfers_from_file_location(
        representation: Representation,
        template_item: TemplateItem,
        transfers: list[TransferItem]
) -> None:
    """Get transfers from FileLocation trait.

    Args:
        representation (Representation): Representation to process.
        template_item (TemplateItem): Template item.
        transfers (list): List of transfers.

    Mutates:
        transfers (list): List of transfers.
        template_item (TemplateItem): Template item.

    """
    path_template_object: "AnatomyStringTemplate" = (
        template_item.template_object["path"]
    )
    file_path = representation.get_trait(FileLocation).file_path
    if isinstance(file_path, str):
        file_path = Path(file_path)

    template_item.template_data["ext"] = (
        file_path.suffix.lstrip(".")
    )
    template_item.template_data.pop("frame", None)
    with contextlib.suppress(MissingTraitError):
        udim = representation.get_trait(UDIM)
        template_item.template_data["udim"] = udim.udim[0]

    template_filled = path_template_object.format_strict(
        template_item.template_data
    )

    # add used values to the template data
    used_values: dict = template_filled.used_values
    template_item.template_data.update(used_values)

    file_loc: FileLocation = representation.get_trait(FileLocation)
    file_path = file_loc.file_path
    if isinstance(file_path, str):
        file_path = Path(file_path)

    transfers.append(
        TransferItem(
            source=file_path,
            destination=Path(template_filled),
            size=file_loc.file_size or TransferItem.get_size(
                file_path),
            checksum=file_loc.file_hash or TransferItem.get_checksum(
                file_path),
            template=template_item.template,
            template_data=template_item.template_data,
            representation=representation,
            related_trait=file_loc
        )
    )
    # add template path and the data to resolve it
    # remove template if already exists
    with contextlib.suppress(ValueError):
        representation.remove_trait(TemplatePath)

    representation.add_trait(TemplatePath(
        template=template_item.template,
        data=template_item.template_data
    ))


def get_transfers_from_bundle(
        representation: Representation,
        template_item: TemplateItem,
        transfers: list[TransferItem]
) -> None:
    """Get transfers from Bundle trait.

    This will be called recursively for each sub-representation in the
    bundle that is a Bundle itself.

    Args:
        representation (Representation): Representation to process.
        template_item (TemplateItem): Template item.
        transfers (list): List of transfers.

    Mutates:
        transfers (list): List of transfers.
        template_item (TemplateItem): Template item.

    """
    bundle: Bundle = representation.get_trait(Bundle)
    for idx, sub_representation_traits in enumerate(bundle.items):
        sub_representation = Representation(
            name=f"{representation.name}_{idx}",
            traits=sub_representation_traits)
        # sub presentation transient:
        sub_representation.add_trait(Transient())
        if sub_representation.contains_trait(FileLocations):
            get_transfers_from_file_locations(
                sub_representation, template_item, transfers
            )
        elif sub_representation.contains_trait(FileLocation):
            get_transfers_from_file_location(
                sub_representation, template_item, transfers
            )
        elif sub_representation.contains_trait(Bundle):
            get_transfers_from_bundle(
                sub_representation, template_item, transfers
            )


def get_transfers_from_file_locations_common_root(
        representation: Representation,
        template_item: TemplateItem,
        transfers: list[TransferItem]
) -> None:
    """Get transfers from FileLocations trait preserving relative hierarchy.

    Args:
        representation (Representation): Representation to process.
        template_item (TemplateItem): Template item.
        transfers (list): List of transfers.

    Mutates:
        transfers (list): List of transfers.
        template_item (TemplateItem): Template item.

    """
    file_locations_trait = representation.get_trait(FileLocations)
    if not file_locations_trait.file_paths:
        return

    try:
        common_root = file_locations_trait.get_common_root()
    except ValueError as exc:
        raise PublishError(
            f"Could not determine common root for representation "
            f"'{representation.name}'"
        ) from exc

    path_template_object = template_item.template_object["path"]
    template_filled = path_template_object.format_strict(
        template_item.template_data
    )

    used_values = template_filled.used_values
    template_item.template_data.update(used_values)

    destination_root = Path(template_filled)
    if destination_root.suffix:
        destination_root = destination_root.parent

    for file_loc in file_locations_trait.file_paths:
        source = file_loc.file_path
        if isinstance(source, str):
            source = Path(source)

        relative_path = source.relative_to(common_root)
        destination = destination_root / relative_path

        transfers.append(
            TransferItem(
                source=source,
                destination=destination,
                size=file_loc.file_size or TransferItem.get_size(source),
                checksum=(
                    file_loc.file_hash
                    or TransferItem.get_checksum(source)
                ),
                template=template_item.template,
                template_data=template_item.template_data,
                representation=representation,
                related_trait=file_loc
            )
        )

    if not representation.contains_trait(TemplatePath):
        representation.add_trait(
            TemplatePath(
                template=template_item.template,
                data=template_item.template_data,
            )
        )


def get_transfers_from_representations(
        instance: pyblish.api.Instance,
        template: AnatomyTemplateItem,
        representations: list[Representation]
) -> list[TransferItem]:
    """Get transfers from representations.

    This method will go through all representations and prepare transfers
    based on the traits they contain. First it will validate the
    representation, and then it will prepare template data for the
    representation. It specifically handles FileLocations, FileLocation,
    Bundle, Sequence and UDIM traits.

    Args:
        instance (pyblish.api.Instance): Instance to process.
        template (AnatomyStringTemplate): Template to use for formatting
            destination paths.
        representations (list[Representation]): List of representations.

    Returns:
        list[TransferItem]: List of transfers.

    Raises:
        PublishError: If representation is invalid.

    """
    instance_template_data: dict[str, str] = {}
    transfers: list[TransferItem] = []
    # prepare template and data to format it
    for representation in representations:

        # validate representation first, this will go through all traits
        # and check if they are valid
        try:
            representation.validate()
        except TraitValidationError as e:
            msg = f"Representation '{representation.name}' is invalid: {e}"
            raise PublishError(msg) from e

        template_data = get_template_data_from_representation(
            representation, instance)
        # add instance based template data

        template_data.update(instance_template_data)

        # treat Variant as `output` in template data
        with contextlib.suppress(MissingTraitError):
            template_data["output"] = (
                representation.get_trait(Variant).variant
            )

        template_item = TemplateItem(
            anatomy=instance.context.data["anatomy"],
            template=template["path"],
            template_data=copy.deepcopy(template_data),
            template_object=template
        )

        if representation.contains_trait(FileLocations):
            # If representation has FileLocations trait (list of files)
            # it can be a Sequence, UDIM tile set, or a group of related
            # files that share a common root and preserve their hierarchy.
            # Note: we do not support yet frame sequence of multiple UDIM
            # tiles in the same representation.
            get_transfers_from_file_locations(
                representation, template_item, transfers
            )
        elif representation.contains_trait(FileLocation):
            # This is just a single file representation
            get_transfers_from_file_location(
                representation, template_item, transfers
            )

        elif representation.contains_trait(Bundle):
            # Bundle groups multiple "sub-representations" together.
            # It has a list of lists with traits, some might be
            # FileLocations,but some might be "file-less" representations
            # or even other bundles.
            get_transfers_from_bundle(
                representation, template_item, transfers
            )
    return transfers


def get_template_data_from_representation(
        representation: Representation,
        instance: pyblish.api.Instance) -> dict:
    """Get template data from representation.

    Using representation traits and data on instance
    prepare data for formatting template.

    Args:
        representation (Representation): Representation to process.
        instance (pyblish.api.Instance): Instance to process.

    Returns:
        dict: Template data.

    """
    template_data = copy.deepcopy(instance.data["anatomyData"])
    template_data["representation"] = representation.name
    template_data["version"] = instance.data["version"]
    # template_data["hierarchy"] = instance.data["hierarchy"]

    # add colorspace data to template data
    if representation.contains_trait(ColorManaged):
        colorspace_data: ColorManaged = representation.get_trait(
            ColorManaged)

        template_data["colorspace"] = {
            "colorspace": colorspace_data.color_space,
            "config": colorspace_data.config
        }

    # add explicit list of traits properties to template data
    # there must be some better way to handle this.

    with contextlib.suppress(MissingTraitError):
        # resolution from PixelBased trait
        template_data["resolution_width"] = representation.get_trait(
            PixelBased).display_window_width
        template_data["resolution_height"] = representation.get_trait(
            PixelBased).display_window_height

    with contextlib.suppress(MissingTraitError):
        # get fps from representation traits
        template_data["fps"] = representation.get_trait(
            FrameRanged).frames_per_second

    with contextlib.suppress(MissingTraitError):
        file_path = representation.get_trait(FileLocation).file_path
        if isinstance(file_path, str):
            file_path = Path(file_path)
        template_data["ext"] = file_path.suffix.lstrip(".")
    if not template_data.get("ext"):
        with contextlib.suppress(MissingTraitError):
            # Try FileLocations trait if FileLocation ext is empty
            file_locations_trait = representation.get_trait(
                FileLocations)
            if file_locations_trait.file_paths:
                first_file_loc = file_locations_trait.file_paths[0]
                file_path = first_file_loc.file_path
                if isinstance(file_path, str):
                    file_path = Path(file_path)
                template_data["ext"] = (file_path.suffix.lstrip("."))
        # Note: handle "output" and "originalBasename"
    return template_data
