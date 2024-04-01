import os

from ayon_core.lib import get_ayon_launcher_args
from ayon_core.lib.execute import run_detached_process
from ayon_core.addon import (
    click_wrap,
    AYONAddon,
    ITrayAction,
    IHostAddon,
)

TRAYPUBLISH_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))


class TrayPublishAddon(AYONAddon, IHostAddon, ITrayAction):
    label = "Publisher"
    name = "traypublisher"
    host_name = "traypublisher"

    def initialize(self, settings):
        self.publish_paths = [
            os.path.join(TRAYPUBLISH_ROOT_DIR, "plugins", "publish")
        ]

    def tray_init(self):
        return

    def on_action_trigger(self):
        self.run_traypublisher()

    def connect_with_addons(self, enabled_modules):
        """Collect publish paths from other modules."""
        publish_paths = self.manager.collect_plugin_paths()["publish"]
        self.publish_paths.extend(publish_paths)

    def run_traypublisher(self):
        args = get_ayon_launcher_args(
            "addon", self.name, "launch"
        )
        run_detached_process(args)

    def cli(self, click_group):
        click_group.add_command(cli_main.to_click_obj())


@click_wrap.group(
    TrayPublishAddon.name,
    help="TrayPublisher related commands.")
def cli_main():
    pass


@cli_main.command()
def launch():
    """Launch TrayPublish tool UI."""

    from ayon_core.tools import traypublisher

    traypublisher.main()
