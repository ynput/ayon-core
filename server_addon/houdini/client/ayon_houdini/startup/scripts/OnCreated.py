# Any code here will run on any node being created in Houdini
# As such, preferably the code here should run fast to avoid slowing down node
# creation. Note: It does not trigger on existing nodes for scene open nor on
# node copy-pasting.
from ayon_core.lib import env_value_to_bool, is_dev_mode_enabled
from ayon_houdini.api import node_wrap


# Allow easier development by automatic reloads
# TODO: remove this
if is_dev_mode_enabled():
    import importlib
    importlib.reload(node_wrap)


if env_value_to_bool("AYON_HOUDINI_AUTOCREATE", default=True):
    node = kwargs["node"]
    node_wrap.autocreate_publishable(node)
