# Metadata keys for work with studio and project overrides
M_OVERRIDDEN_KEY = "__overriden_keys__"
# Metadata key for storing dynamic created labels
M_DYNAMIC_KEY_LABEL = "__dynamic_keys_labels__"

METADATA_KEYS = frozenset([
    M_OVERRIDDEN_KEY,
    M_DYNAMIC_KEY_LABEL
])

# Keys where studio's system overrides are stored
SYSTEM_SETTINGS_KEY = "system_settings"
PROJECT_SETTINGS_KEY = "project_settings"

DEFAULT_PROJECT_KEY = "__default_project__"


__all__ = (
    "M_OVERRIDDEN_KEY",
    "M_DYNAMIC_KEY_LABEL",

    "METADATA_KEYS",

    "SYSTEM_SETTINGS_KEY",
    "PROJECT_SETTINGS_KEY",

    "DEFAULT_PROJECT_KEY",
)
