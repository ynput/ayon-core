# -*-coding: utf-8 -*-
import hou

import pyblish.api
from ayon_core.pipeline.publish import RepairContextAction
from ayon_core.pipeline import PublishValidationError

from ayon_houdini.api import lib, plugin


class ValidateRemotePublishOutNode(plugin.HoudiniContextPlugin):
    """Validate the remote publish out node exists for Deadline to trigger."""

    order = pyblish.api.ValidatorOrder - 0.4
    families = ["*"]
    targets = ["deadline"]
    label = "Remote Publish ROP node"
    actions = [RepairContextAction]

    def process(self, context):

        cmd = "import colorbleed.lib; colorbleed.lib.publish_remote()"

        node = hou.node("/out/REMOTE_PUBLISH")
        if not node:
            raise RuntimeError("Missing REMOTE_PUBLISH node.")

        # We ensure it's a shell node and that it has the pre-render script
        # set correctly. Plus the shell script it will trigger should be
        # completely empty (doing nothing)
        if node.type().name() != "shell":
            self.raise_error("Must be shell ROP node")
        if node.parm("command").eval() != "":
            self.raise_error("Must have no command")
        if node.parm("shellexec").eval():
            self.raise_error("Must not execute in shell")
        if node.parm("prerender").eval() != cmd:
            self.raise_error("REMOTE_PUBLISH node does not have "
                             "correct prerender script.")
        if node.parm("lprerender").eval() != "python":
            self.raise_error("REMOTE_PUBLISH node prerender script "
                             "type not set to 'python'")

    @classmethod
    def repair(cls, context):
        """(Re)create the node if it fails to pass validation."""
        lib.create_remote_publish_node(force=True)

    def raise_error(self, message):
        raise PublishValidationError(message)
