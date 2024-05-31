# -*- coding: utf-8 -*-
import os
import hou

import pyblish.api
from ayon_core.pipeline import (
    PublishValidationError,
    OptionalPyblishPluginMixin
)
from ayon_core.pipeline.publish import (
    RepairAction,
    get_plugin_settings,
    apply_plugin_settings_automatically
)

from ayon_houdini.api import plugin
from ayon_houdini.api.action import SelectROPAction


class ResetViewSpaceAction(RepairAction):
    label = "Reset OCIO colorspace parm"
    icon = "mdi.monitor"


class ValidateReviewColorspace(plugin.HoudiniInstancePlugin,
                               OptionalPyblishPluginMixin):
    """Validate Review Colorspace parameters.

    It checks if 'OCIO Colorspace' parameter was set to valid value.
    """

    order = pyblish.api.ValidatorOrder + 0.1
    families = ["review"]
    label = "Validate Review Colorspace"
    actions = [ResetViewSpaceAction, SelectROPAction]

    optional = True
    review_color_space = ""

    @classmethod
    def apply_settings(cls, project_settings):
        # Preserve automatic settings applying logic
        settings = get_plugin_settings(plugin=cls,
                                       project_settings=project_settings,
                                       log=cls.log,
                                       category="houdini")
        apply_plugin_settings_automatically(cls, settings, logger=cls.log)

        # workfile settings added in '0.2.13'
        color_settings = project_settings["houdini"]["imageio"].get(
            "workfile", {}
        )
        # Add review color settings
        if color_settings.get("enabled"):
            cls.review_color_space = color_settings.get("review_color_space")


    def process(self, instance):

        rop_node = hou.node(instance.data["instance_node"])

        # This plugin is triggered when marking render as reviewable.
        # Therefore, this plugin will run on over wrong instances.
        # TODO: Don't run this plugin on wrong instances.
        # This plugin should run only on review product type
        # with instance node of opengl type.
        if rop_node.type().name() != "opengl":
            self.log.debug("Skipping Validation. Rop node {} "
                           "is not an OpenGl node.".format(rop_node.path()))
            return

        if not self.is_active(instance.data):
            return

        if os.getenv("OCIO") is None:
            self.log.debug(
                "Using Houdini's Default Color Management, "
                " skipping check.."
            )
            return

        if rop_node.evalParm("colorcorrect") != 2:
            # any colorspace settings other than default requires
            # 'Color Correct' parm to be set to 'OpenColorIO'
            raise PublishValidationError(
                "'Color Correction' parm on '{}' ROP must be set to"
                " 'OpenColorIO'".format(rop_node.path())
            )

        current_color_space = rop_node.evalParm("ociocolorspace")
        if current_color_space not in hou.Color.ocio_spaces():
            raise PublishValidationError(
                "Invalid value: Colorspace name doesn't exist.\n"
                "Check 'OCIO Colorspace' parameter on '{}' ROP"
                .format(rop_node.path())
            )

        # if houdini/imageio/workfile is enabled and
        #  Review colorspace setting is empty then this check should
        #  actually check if the current_color_space setting equals
        #  the default colorspace value.
        # However, it will make the black cmd screen show up more often
        #   which is very annoying.
        if self.review_color_space and \
                self.review_color_space != current_color_space:

            raise PublishValidationError(
                "Invalid value: Colorspace name doesn't match"
                "the Colorspace specified in settings."
            )

    @classmethod
    def repair(cls, instance):
        """Reset view colorspace.

        It is used to set colorspace on opengl node.

        It uses the colorspace value specified in the Houdini addon settings.
        If the value in the Houdini addon settings is empty,
            it will fall to the default colorspace.

        Note:
            This repair action assumes that OCIO is enabled.
            As if OCIO is disabled the whole validation is skipped
            and this repair action won't show up.
        """
        from ayon_houdini.api.lib import set_review_color_space

        # Fall to the default value if cls.review_color_space is empty.
        if not cls.review_color_space:
            # cls.review_color_space is an empty string
            #  when the imageio/workfile setting is disabled or
            #  when the Review colorspace setting is empty.
            from ayon_houdini.api.colorspace import get_default_display_view_colorspace  # noqa
            cls.review_color_space = get_default_display_view_colorspace()

        rop_node = hou.node(instance.data["instance_node"])
        set_review_color_space(rop_node,
                               cls.review_color_space,
                               cls.log)
