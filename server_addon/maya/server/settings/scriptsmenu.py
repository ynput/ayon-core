import json

from pydantic import validator
from ayon_server.exceptions import BadRequestException
from ayon_server.settings import BaseSettingsModel, SettingsField


class ScriptsmenuSubmodel(BaseSettingsModel):
    """Item Definition"""
    _isGroup = True
    type: str = SettingsField(title="Type")
    command: str = SettingsField(title="Command")
    sourcetype: str = SettingsField(title="Source Type")
    title: str = SettingsField(title="Title")
    tooltip: str = SettingsField(title="Tooltip")
    tags: list[str] = SettingsField(
        default_factory=list, title="A list of tags"
    )


class ScriptsmenuModel(BaseSettingsModel):
    """Add a custom scripts menu to Maya"""
    _isGroup = True

    name: str = SettingsField(title="Menu Name")
    use_json_definition: bool = SettingsField(
        title="Use Raw JSON Definition",
        description="When enabled, the definition field will be ignored. "
                    "Instead the menu will be build from the raw JSON "
                    "definition below it."
    )
    definition: list[ScriptsmenuSubmodel] = SettingsField(
        default_factory=list,
        title="Menu Definition",
        description="Scriptmenu Items Definition"
    )

    definition_json: str = SettingsField(
        "[]", title="Definition JSON", widget="textarea",
        description=(
            "When Use Raw JSON definition is enabled this field will be used "
            "to put the direct JSON content instead of using the definition "
            "menu builder UI above. For more details on the JSON format, see "
            "[here](https://github.com/Colorbleed/scriptsmenu?tab=readme-ov-file#configuration)."  # noqa: E501
        )
    )

    @validator("definition_json")
    def validate_json(cls, value):
        if not value.strip():
            return "[]"
        try:
            converted_value = json.loads(value)
            success = isinstance(converted_value, list)
        except json.JSONDecodeError:
            success = False

        if not success:
            raise BadRequestException(
                "The definition can't be parsed as json list object"
            )
        return value


DEFAULT_SCRIPTSMENU_SETTINGS = {
    "name": "Custom Tools",
    "use_json_definition": False,
    "definition": [
        {
            "type": "action",
            "command": "import openpype.hosts.maya.api.commands as op_cmds; op_cmds.edit_shader_definitions()",
            "sourcetype": "python",
            "title": "Edit shader name definitions",
            "tooltip": "Edit shader name definitions used in validation and renaming.",
            "tags": [
                "pipeline",
                "shader"
            ]
        }
    ],
    "definition_raw": ""
}
