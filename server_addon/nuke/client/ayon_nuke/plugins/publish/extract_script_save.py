import nuke
import pyblish.api


class ExtractScriptSave(pyblish.api.InstancePlugin):
    """Save current Nuke workfile script"""
    label = 'Script Save'
    order = pyblish.api.ExtractorOrder - 0.1
    hosts = ["nuke"]

    settings_category = "nuke"

    def process(self, instance):

        self.log.debug('Saving current script')
        nuke.scriptSave()
