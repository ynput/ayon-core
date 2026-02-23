from __future__ import annotations

import uuid
from typing import Any

from ayon_core.lib.attribute_definitions import (
    AbstractAttrDef,
    UILabelDef,
    BoolDef,
    TextDef,
    NumberDef,
    EnumDef,
    HiddenDef,
)


def webaction_fields_to_attribute_defs(
    fields: list[dict[str, Any]]
) -> list[AbstractAttrDef]:
    """Helper function to convert fields definition from webactions form.

    Convert form fields to attribute definitions to be able to display them
        using attribute definitions.

    Args:
        fields (list[dict[str, Any]]): Fields from webaction form.

    Returns:
        list[AbstractAttrDef]: Converted attribute definitions.

    """
    attr_defs = []
    for field in fields:
        field_type = field["type"]
        attr_def = None
        if field_type == "label":
            label = field.get("value")
            if label is None:
                label = field.get("text")
            attr_def = UILabelDef(
                label, key=uuid.uuid4().hex
            )
        elif field_type == "boolean":
            value = field["value"]
            if isinstance(value, str):
                value = value.lower() == "true"

            attr_def = BoolDef(
                field["name"],
                default=value,
                label=field.get("label"),
            )
        elif field_type == "text":
            attr_def = TextDef(
                field["name"],
                default=field.get("value"),
                label=field.get("label"),
                placeholder=field.get("placeholder"),
                multiline=field.get("multiline", False),
                regex=field.get("regex"),
                # syntax=field["syntax"],
            )
        elif field_type in ("integer", "float"):
            value = field.get("value")
            if isinstance(value, str):
                if field_type == "integer":
                    value = int(value)
                else:
                    value = float(value)
            attr_def = NumberDef(
                field["name"],
                default=value,
                label=field.get("label"),
                decimals=0 if field_type == "integer" else 5,
                # placeholder=field.get("placeholder"),
                minimum=field.get("min"),
                maximum=field.get("max"),
            )
        elif field_type in ("select", "multiselect"):
            attr_def = EnumDef(
                field["name"],
                items=field["options"],
                default=field.get("value"),
                label=field.get("label"),
                multiselection=field_type == "multiselect",
            )
        elif field_type == "hidden":
            attr_def = HiddenDef(
                field["name"],
                default=field.get("value"),
            )

        if attr_def is None:
            print(f"Unknown config field type: {field_type}")
            attr_def = UILabelDef(
                f"Unknown field type '{field_type}",
                key=uuid.uuid4().hex
            )
        attr_defs.append(attr_def)
    return attr_defs
