# -*- coding: utf-8 -*-
import hou

import pyblish.api
from ayon_core.pipeline import PublishValidationError

from ayon_houdini.api import plugin


class ValidateSceneReview(plugin.HoudiniInstancePlugin):
    """Validator Some Scene Settings before publishing the review
        1. Scene Path
        2. Resolution
    """

    order = pyblish.api.ValidatorOrder
    families = ["review"]
    label = "Scene Setting for review"

    def process(self, instance):

        report = []
        instance_node = hou.node(instance.data.get("instance_node"))

        # This plugin is triggered when marking render as reviewable.
        # Therefore, this plugin will run on over wrong instances.
        # TODO: Don't run this plugin on wrong instances.
        # This plugin should run only on review product type
        # with instance node of opengl type.
        if instance_node.type().name() != "opengl":
            self.log.debug("Skipping Validation. Rop node {} "
                           "is not an OpenGl node.".format(instance_node.path()))
            return

        invalid = self.get_invalid_scene_path(instance_node)
        if invalid:
            report.append(invalid)

        invalid = self.get_invalid_camera_path(instance_node)
        if invalid:
            report.append(invalid)

        invalid = self.get_invalid_resolution(instance_node)
        if invalid:
            report.extend(invalid)

        if report:
            raise PublishValidationError(
                "\n\n".join(report),
                title=self.label)

    def get_invalid_scene_path(self, rop_node):
        scene_path_parm = rop_node.parm("scenepath")
        scene_path_node = scene_path_parm.evalAsNode()
        if not scene_path_node:
            path = scene_path_parm.evalAsString()
            return "Scene path does not exist: '{}'".format(path)

    def get_invalid_camera_path(self, rop_node):
        camera_path_parm = rop_node.parm("camera")
        camera_node = camera_path_parm.evalAsNode()
        path = camera_path_parm.evalAsString()
        if not camera_node:
            return "Camera path does not exist: '{}'".format(path)
        type_name = camera_node.type().name()
        if type_name != "cam":
            return "Camera path is not a camera: '{}' (type: {})".format(
                path, type_name
            )

    def get_invalid_resolution(self, rop_node):

        # The resolution setting is only used when Override Camera Resolution
        # is enabled. So we skip validation if it is disabled.
        override = rop_node.parm("tres").eval()
        if not override:
            return

        invalid = []
        res_width = rop_node.parm("res1").eval()
        res_height = rop_node.parm("res2").eval()
        if res_width == 0:
            invalid.append("Override Resolution width is set to zero.")
        if res_height == 0:
            invalid.append("Override Resolution height is set to zero")

        return invalid
