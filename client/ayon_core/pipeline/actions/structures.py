from dataclasses import dataclass
from typing import Optional, Any

from ayon_core.lib.attribute_definitions import (
    AbstractAttrDef,
    serialize_attr_defs,
    deserialize_attr_defs,
)


@dataclass
class ActionForm:
    """Form for loader action.

    If an action needs to collect information from a user before or during of
        the action execution, it can return a response with a form. When the
        form is submitted, a new execution of the action is triggered.

    It is also possible to just show a label message without the submit
        button to make sure the user has seen the message.

    Attributes:
        title (str): Title of the form -> title of the window.
        fields (list[AbstractAttrDef]): Fields of the form.
        submit_label (Optional[str]): Label of the submit button. Is hidden
            if is set to None.
        submit_icon (Optional[dict[str, Any]]): Icon definition of the submit
            button.
        cancel_label (Optional[str]): Label of the cancel button. Is hidden
            if is set to None. User can still close the window tho.
        cancel_icon (Optional[dict[str, Any]]): Icon definition of the cancel
            button.

    """
    title: str
    fields: list[AbstractAttrDef]
    submit_label: Optional[str] = "Submit"
    submit_icon: Optional[dict[str, Any]] = None
    cancel_label: Optional[str] = "Cancel"
    cancel_icon: Optional[dict[str, Any]] = None

    def to_json_data(self) -> dict[str, Any]:
        fields = self.fields
        if fields is not None:
            fields = serialize_attr_defs(fields)
        return {
            "title": self.title,
            "fields": fields,
            "submit_label": self.submit_label,
            "submit_icon": self.submit_icon,
            "cancel_label": self.cancel_label,
            "cancel_icon": self.cancel_icon,
        }

    @classmethod
    def from_json_data(cls, data: dict[str, Any]) -> "ActionForm":
        fields = data["fields"]
        if fields is not None:
            data["fields"] = deserialize_attr_defs(fields)
        return cls(**data)
