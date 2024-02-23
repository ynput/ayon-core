from ayon_server.settings import BaseSettingsModel, SettingsField


class ZbrushSettings(BaseSettingsModel):
    stop_timer_on_application_exit: bool = SettingsField(
        title="Stop timer on application exit")


DEFAULT_VALUES = {
    "stop_timer_on_application_exit": False
}
