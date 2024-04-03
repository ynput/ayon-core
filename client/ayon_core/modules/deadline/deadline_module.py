import os
import sys

import requests
import six

from ayon_core.lib import Logger
from ayon_core.modules import AYONAddon, IPluginPaths


class DeadlineWebserviceError(Exception):
    """
    Exception to throw when connection to Deadline server fails.
    """


class DeadlineModule(AYONAddon, IPluginPaths):
    name = "deadline"

    def initialize(self, studio_settings):
        # This module is always enabled
        deadline_urls = {}
        enabled = self.name in studio_settings
        if enabled:
            deadline_settings = studio_settings[self.name]
            deadline_urls = {
                url_item["name"]: url_item["value"]
                for url_item in deadline_settings["deadline_urls"]
            }

        if enabled and not deadline_urls:
            enabled = False
            self.log.warning((
                "Deadline Webservice URLs are not specified. Disabling addon."
            ))

        self.enabled = enabled
        self.deadline_urls = deadline_urls

    def get_plugin_paths(self):
        """Deadline plugin paths."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return {
            "publish": [os.path.join(current_dir, "plugins", "publish")]
        }

    @staticmethod
    def get_repo_dir(webservice, log=None):
        """Get repository root folder from Deadline.
        Args:
            webservice (str): Server url.
            log (Logger)
        Returns:
            str: Repository root folder.
        Throws:
            RuntimeError: If deadline webservice is unreachable.

        """

        url = "{}/api/repository?Directory=root".format(webservice)
        return DeadlineModule._call_webservice(url, log)

    @staticmethod
    def get_deadline_pools(webservice, log=None):
        """Get pools from Deadline.
        Args:
            webservice (str): Server url.
            log (Logger)
        Returns:
            list: Pools.
        Throws:
            RuntimeError: If deadline webservice is unreachable.

        """

        url = "{}/api/pools?NamesOnly=true".format(webservice)
        return DeadlineModule._call_webservice(url, log)

    @staticmethod
    def _call_webservice(url, log=None):
        from .abstract_submit_deadline import requests_get

        if not log:
            log = Logger.get_logger(__name__)
        try:
            response = requests_get(url)
        except requests.exceptions.ConnectionError as exc:
            msg = 'Cannot connect to DL web service {}'.format(url)
            log.error(msg)
            six.reraise(
                DeadlineWebserviceError,
                DeadlineWebserviceError('{} - {}'.format(msg, exc)),
                sys.exc_info()[2])
        if not response.ok:
            log.warning("No response retrieved")
            return []

        return response.json()
