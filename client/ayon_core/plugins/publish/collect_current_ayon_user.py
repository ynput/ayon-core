import pyblish.api

from ayon_core.lib import get_ayon_username


class CollectCurrentAYONUser(pyblish.api.ContextPlugin):
    """Inject the currently logged on user into the Context"""

    # Order must be after default pyblish-base CollectCurrentUser
    order = pyblish.api.CollectorOrder + 0.001
    label = "Collect AYON User"

    def process(self, context):
        user = get_ayon_username()
        context.data["user"] = user
        self.log.debug("Collected user \"{}\"".format(user))
