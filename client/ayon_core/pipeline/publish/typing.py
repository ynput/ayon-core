from typing import Type

import pyblish.api


# The pyblish logic is working with classes, not with objects
PluginType = Type[pyblish.api.Plugin]
ActionType = Type[pyblish.api.Action]
