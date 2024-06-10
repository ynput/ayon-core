# Copyright Epic Games, Inc. All Rights Reserved

# Third-party
import unreal


@unreal.uclass()
class BaseActionMenuEntry(unreal.ToolMenuEntryScript):
    """
    This is a custom Unreal Class that adds executable python menus to the
    Editor
    """

    def __init__(self, callable_method, parent=None):
        """
        Constructor
        :param callable_method:  Callable method to execute
        """
        super(BaseActionMenuEntry, self).__init__()

        self._callable = callable_method
        self.parent = parent

    @unreal.ufunction(override=True)
    def execute(self, context):
        """
        Executes the callable method
        :param context:
        :return:
        """
        self._callable()

    @unreal.ufunction(override=True)
    def can_execute(self, context):
        """
        Determines if a menu can be executed
        :param context:
        :return:
        """
        return True

    @unreal.ufunction(override=True)
    def get_tool_tip(self, context):
        """
        Returns the tool tip for the menu
        :param context:
        :return:
        """
        return self.data.tool_tip

    @unreal.ufunction(override=True)
    def get_label(self, context):
        """
        Returns the label of the menu
        :param context:
        :return:
        """
        return self.data.name
