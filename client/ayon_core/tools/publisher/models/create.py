from ayon_core.lib.attribute_definitions import (
    serialize_attr_defs,
    deserialize_attr_defs,
)
from ayon_core.pipeline.create import (
    AutoCreator,
    HiddenCreator,
    Creator,
)


class CreatorType:
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name

    def __eq__(self, other):
        return self.name == str(other)

    def __ne__(self, other):
        # This is implemented only because of Python 2
        return not self == other


class CreatorTypes:
    base = CreatorType("base")
    auto = CreatorType("auto")
    hidden = CreatorType("hidden")
    artist = CreatorType("artist")

    @classmethod
    def from_str(cls, value):
        for creator_type in (
            cls.base,
            cls.auto,
            cls.hidden,
            cls.artist
        ):
            if value == creator_type:
                return creator_type
        raise ValueError("Unknown type \"{}\"".format(str(value)))


class CreatorItem:
    """Wrapper around Creator plugin.

    Object can be serialized and recreated.
    """

    def __init__(
        self,
        identifier,
        creator_type,
        product_type,
        label,
        group_label,
        icon,
        description,
        detailed_description,
        default_variant,
        default_variants,
        create_allow_context_change,
        create_allow_thumbnail,
        show_order,
        pre_create_attributes_defs,
    ):
        self.identifier = identifier
        self.creator_type = creator_type
        self.product_type = product_type
        self.label = label
        self.group_label = group_label
        self.icon = icon
        self.description = description
        self.detailed_description = detailed_description
        self.default_variant = default_variant
        self.default_variants = default_variants
        self.create_allow_context_change = create_allow_context_change
        self.create_allow_thumbnail = create_allow_thumbnail
        self.show_order = show_order
        self.pre_create_attributes_defs = pre_create_attributes_defs

    def get_group_label(self):
        return self.group_label

    @classmethod
    def from_creator(cls, creator):
        if isinstance(creator, AutoCreator):
            creator_type = CreatorTypes.auto
        elif isinstance(creator, HiddenCreator):
            creator_type = CreatorTypes.hidden
        elif isinstance(creator, Creator):
            creator_type = CreatorTypes.artist
        else:
            creator_type = CreatorTypes.base

        description = None
        detail_description = None
        default_variant = None
        default_variants = None
        pre_create_attr_defs = None
        create_allow_context_change = None
        create_allow_thumbnail = None
        show_order = creator.order
        if creator_type is CreatorTypes.artist:
            description = creator.get_description()
            detail_description = creator.get_detail_description()
            default_variant = creator.get_default_variant()
            default_variants = creator.get_default_variants()
            pre_create_attr_defs = creator.get_pre_create_attr_defs()
            create_allow_context_change = creator.create_allow_context_change
            create_allow_thumbnail = creator.create_allow_thumbnail
            show_order = creator.show_order

        identifier = creator.identifier
        return cls(
            identifier,
            creator_type,
            creator.product_type,
            creator.label or identifier,
            creator.get_group_label(),
            creator.get_icon(),
            description,
            detail_description,
            default_variant,
            default_variants,
            create_allow_context_change,
            create_allow_thumbnail,
            show_order,
            pre_create_attr_defs,
        )

    def to_data(self):
        pre_create_attributes_defs = None
        if self.pre_create_attributes_defs is not None:
            pre_create_attributes_defs = serialize_attr_defs(
                self.pre_create_attributes_defs
            )

        return {
            "identifier": self.identifier,
            "creator_type": str(self.creator_type),
            "product_type": self.product_type,
            "label": self.label,
            "group_label": self.group_label,
            "icon": self.icon,
            "description": self.description,
            "detailed_description": self.detailed_description,
            "default_variant": self.default_variant,
            "default_variants": self.default_variants,
            "create_allow_context_change": self.create_allow_context_change,
            "create_allow_thumbnail": self.create_allow_thumbnail,
            "show_order": self.show_order,
            "pre_create_attributes_defs": pre_create_attributes_defs,
        }

    @classmethod
    def from_data(cls, data):
        pre_create_attributes_defs = data["pre_create_attributes_defs"]
        if pre_create_attributes_defs is not None:
            data["pre_create_attributes_defs"] = deserialize_attr_defs(
                pre_create_attributes_defs
            )

        data["creator_type"] = CreatorTypes.from_str(data["creator_type"])
        return cls(**data)