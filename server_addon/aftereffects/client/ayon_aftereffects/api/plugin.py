import six
from abc import ABCMeta

from ayon_core.pipeline import LoaderPlugin
from .launch_logic import get_stub


@six.add_metaclass(ABCMeta)
class AfterEffectsLoader(LoaderPlugin):
    @staticmethod
    def get_stub():
        return get_stub()
