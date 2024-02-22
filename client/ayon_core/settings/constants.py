# Metadata keys for work with studio and project overrides
M_OVERRIDDEN_KEY = "__overriden_keys__"
# Metadata key for storing dynamic created labels
M_DYNAMIC_KEY_LABEL = "__dynamic_keys_labels__"

METADATA_KEYS = frozenset([
    M_OVERRIDDEN_KEY,
    M_DYNAMIC_KEY_LABEL
])

# Keys where studio's system overrides are stored
PROJECT_SETTINGS_KEY = "project_settings"


__all__ = (
    "M_OVERRIDDEN_KEY",
    "M_DYNAMIC_KEY_LABEL",

    "METADATA_KEYS",

    "PROJECT_SETTINGS_KEY",
)
