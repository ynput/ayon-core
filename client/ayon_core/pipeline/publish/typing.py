from typing import Type

import pyblish.api

from .publish_plugins import AYONPyblishPluginMixin


class AYONPublishPlugin(pyblish.api.Plugin, AYONPyblishPluginMixin):
    pass


# The pyblish logic is working with classes, not with objects
PluginType = Type[pyblish.api.Plugin]
ActionType = Type[pyblish.api.Action]

PublishPluginType = PluginType
AYONPublishPluginType = Type[AYONPublishPlugin]
