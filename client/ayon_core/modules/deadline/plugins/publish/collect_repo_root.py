# -*- coding: utf-8 -*-
import pyblish.api
from ayon_core.pipeline.publish import AYONPyblishPluginMixin
from ayon_core.modules.deadline.deadline_module import DeadlineModule


class CollectDeadlineRepoRoot(pyblish.api.InstancePlugin,
                              AYONPyblishPluginMixin):
    """Collect repo root folder

    Repo root is necessary to provide absolute path for pre load script for
    Perforce

    """

    order = pyblish.api.CollectorOrder + 0.420
    label = "Collect Deadline Repository Dir"
    hosts = ["unreal"]

    families = ["render"]

    def process(self, instance):
        if not instance.data.get("farm"):
            self.log.debug("Skipping local instance.")
            return

        deadline_url = self.get_deadline_url(instance)
        get_repo_dir = self.get_repo_dir(deadline_url)

        # todo: refactor after DL password is merged
        instance.data["deadlineRepoRoot"] = get_repo_dir

    def get_deadline_url(self, instance):
        # get default deadline webservice url from deadline module
        deadline_url = instance.context.data["defaultDeadline"]
        if instance.data.get("deadlineUrl"):
            # if custom one is set in instance, use that
            deadline_url = instance.data.get("deadlineUrl")
        return deadline_url

    def get_repo_dir(self, deadline_url):
        repo_dir = DeadlineModule.get_repo_dir(deadline_url,
                                               log=self.log)
        self.log.info("Repo dir: {}".format(repo_dir))

        return repo_dir

