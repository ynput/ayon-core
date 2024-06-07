import os
import sys
import contextlib
import traceback

from ayon_core.lib import env_value_to_bool, Logger, is_in_tests
from ayon_core.addon import AddonsManager
from ayon_core.pipeline import install_host
from ayon_core.tools.utils import host_tools
from ayon_core.tools.utils import get_ayon_qt_app

from .launch_logic import ProcessLauncher, stub

log = Logger.get_logger(__name__)


def safe_excepthook(*args):
    traceback.print_exception(*args)


def main(*subprocess_args):
    from ayon_photoshop.api import PhotoshopHost

    host = PhotoshopHost()
    install_host(host)

    sys.excepthook = safe_excepthook

    # coloring in StdOutBroker
    os.environ["AYON_LOG_NO_COLORS"] = "0"
    app = get_ayon_qt_app()
    app.setQuitOnLastWindowClosed(False)

    launcher = ProcessLauncher(subprocess_args)
    launcher.start()

    if env_value_to_bool("HEADLESS_PUBLISH"):
        manager = AddonsManager()
        webpublisher_addon = manager["webpublisher"]
        launcher.execute_in_main_thread(
            webpublisher_addon.headless_publish,
            log,
            "ClosePS",
            is_in_tests()
        )
    elif env_value_to_bool("AVALON_PHOTOSHOP_WORKFILES_ON_LAUNCH",
                           default=True):

        launcher.execute_in_main_thread(
            host_tools.show_workfiles,
            save=env_value_to_bool("WORKFILES_SAVE_AS")
        )

    sys.exit(app.exec_())


@contextlib.contextmanager
def maintained_selection():
    """Maintain selection during context."""
    selection = stub().get_selected_layers()
    try:
        yield selection
    finally:
        stub().select_layers(selection)


@contextlib.contextmanager
def maintained_visibility(layers=None):
    """Maintain visibility during context.

    Args:
        layers (list) of PSItem (used for caching)
    """
    visibility = {}
    if not layers:
        layers = stub().get_layers()
    for layer in layers:
        visibility[layer.id] = layer.visible
    try:
        yield
    finally:
        for layer in layers:
            stub().set_visible(layer.id, visibility[layer.id])
            pass
