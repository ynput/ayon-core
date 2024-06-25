from ayon_server.settings import (
    BaseSettingsModel,
    SettingsField,
)

from .main import defined_deadline_ws_name_enum_resolver


class CredentialPerServerModel(BaseSettingsModel):
    """Provide credentials for configured DL servers"""
    _layout = "expanded"
    server_name: str = SettingsField(
        "",
        title="DL server name",
        enum_resolver=defined_deadline_ws_name_enum_resolver
    )
    username: str = SettingsField("", title="Username")
    password: str = SettingsField("", title="Password")


class DeadlineSiteSettings(BaseSettingsModel):
    local_settings: list[CredentialPerServerModel] = SettingsField(
        default_factory=list,
        title="Local setting",
        description=(
            "Please provide credentials for configured Deadline servers"
        ),
    )
