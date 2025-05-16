"""Create module for Ayon Core."""
from .constants import (
    DEFAULT_PRODUCT_TEMPLATE,
    DEFAULT_VARIANT_VALUE,
    PRE_CREATE_THUMBNAIL_KEY,
    PRODUCT_NAME_ALLOWED_SYMBOLS,
)
from .context import CreateContext
from .creator_plugins import (
    AutoCreator,
    BaseCreator,
    Creator,
    HiddenCreator,
    cache_and_get_instances,
    deregister_creator_plugin,
    deregister_creator_plugin_path,
    discover_creator_plugins,
    discover_legacy_creator_plugins,
    get_legacy_creator_by_name,
    register_creator_plugin,
    register_creator_plugin_path,
)
from .exceptions import (
    ConvertorsConversionFailed,
    ConvertorsFindFailed,
    ConvertorsOperationFailed,
    CreatorError,
    CreatorsCollectionFailed,
    CreatorsCreateFailed,
    CreatorsOperationFailed,
    CreatorsRemoveFailed,
    CreatorsSaveFailed,
    HostMissRequiredMethod,
    ImmutableKeyError,
    TaskNotSetError,
    TemplateFillError,
    UnavailableSharedData,
)
from .legacy_create import (
    LegacyCreator,
    legacy_create,
)
from .product_name import (
    get_product_name,
    get_product_name_template,
)
from .structures import (
    AttributeValues,
    ConvertorItem,
    CreatedInstance,
    CreatorAttributeValues,
    PublishAttributes,
    PublishAttributeValues,
)
from .utils import (
    get_last_versions_for_instances,
    get_next_versions_for_instances,
)

__all__ = (
    "DEFAULT_PRODUCT_TEMPLATE",
    "DEFAULT_VARIANT_VALUE",
    "PRE_CREATE_THUMBNAIL_KEY",
    "PRODUCT_NAME_ALLOWED_SYMBOLS",

    "AttributeValues",
    "AutoCreator",
    "BaseCreator",
    "ConvertorItem",
    "ConvertorsConversionFailed",
    "ConvertorsFindFailed",
    "ConvertorsOperationFailed",
    "CreateContext",
    "CreatedInstance",
    "Creator",
    "CreatorAttributeValues",
    "CreatorError",
    "CreatorError",
    "CreatorsCollectionFailed",
    "CreatorsCreateFailed",
    "CreatorsOperationFailed",
    "CreatorsRemoveFailed",
    "CreatorsSaveFailed",
    "HiddenCreator",
    "HostMissRequiredMethod",
    "ImmutableKeyError",
    "LegacyCreator",
    "PublishAttributeValues",
    "PublishAttributes",
    "TaskNotSetError",
    "TemplateFillError",
    "UnavailableSharedData",

    "cache_and_get_instances",
    "deregister_creator_plugin",
    "deregister_creator_plugin_path",
    "discover_creator_plugins",
    "discover_legacy_creator_plugins",
    "get_last_versions_for_instances",
    "get_legacy_creator_by_name",
    "get_next_versions_for_instances",
    "get_product_name",
    "get_product_name_template",
    "legacy_create",
    "register_creator_plugin",
    "register_creator_plugin_path",
)
