# Copyright Epic Games, Inc. All Rights Reserved

# Third party
import unreal

# Internal
from .base_menu_action import BaseActionMenuEntry


class DeadlineToolBarMenu(object):
    """
    Class for Deadline Unreal Toolbar menu
    """

    TOOLBAR_NAME = "Deadline"
    TOOLBAR_OWNER = "deadline.toolbar.menu"
    PARENT_MENU = "LevelEditor.MainMenu"
    SECTION_NAME = "deadline_section"

    def __init__(self):
        """Constructor"""

        # Keep reference to tool menus from Unreal
        self._tool_menus = None

        # Keep track of all the action menus that have been registered to
        # Unreal. Without keeping these around, the Unreal GC will remove the
        # menu objects and break the in-engine menu
        self.menu_entries = []

        self._top_level_menu = f"{self.PARENT_MENU}.{self.TOOLBAR_NAME}"

        self._initialize_toolbar()

        # Set up a shutdown callback for when python is existing to cleanly
        # clear the menus
        unreal.register_python_shutdown_callback(self._shutdown)

    @property
    def _unreal_tools_menu(self):
        """Get Unreal Editor Tool menu"""
        if not self._tool_menus or self._tool_menus is None:
            self._tool_menus = unreal.ToolMenus.get()

        return self._tool_menus

    def _initialize_toolbar(self):
        """Initialize our custom toolbar with the Editor"""

        tools_menu = self._unreal_tools_menu

        # Create the custom menu and add it to Unreal Main Menu
        main_menu = tools_menu.extend_menu(self.PARENT_MENU)

        # Create the submenu object
        main_menu.add_sub_menu(
            self.TOOLBAR_OWNER,
            "",
            self.TOOLBAR_NAME,
            self.TOOLBAR_NAME
        )

        # Register the custom deadline menu to the Editor Main Menu
        tools_menu.register_menu(
            self._top_level_menu,
            "",
            unreal.MultiBoxType.MENU,
            False
        )

    def _shutdown(self):
        """Method to call when the editor is shutting down"""

        # Unregister all menus owned by the integration
        self._tool_menus.unregister_owner_by_name(self.TOOLBAR_OWNER)

        # Clean up all the menu instances we are tracking
        del self.menu_entries[:]

    def register_submenu(
        self,
        menu_name,
        callable_method,
        label_name=None,
        description=None
    ):
        """
        Register a menu to the toolbar.
        Note: This currently creates a flat submenu in the Main Menu

        :param str menu_name: The name of the submenu
        :param object callable_method: A callable method to execute on menu
            activation
        :param str label_name: Nice Label name to display the menu
        :param str description: Description of the menu. This will eb
                displayed in the tooltip
        """

        # Get an instance of a custom `unreal.ToolMenuEntryScript` class
        # Wrap it in a try except block for instances where
        # the unreal module has not loaded yet.

        try:
            entry = BaseActionMenuEntry(
                callable_method,
                parent=self
            )
            menu_entry_name = menu_name.replace(" ", "")

            entry.init_entry(
                self.TOOLBAR_OWNER,
                f"{self._top_level_menu}.{menu_entry_name}",
                menu_entry_name,
                label_name or menu_name,
                tool_tip=description or ""
            )

            # Add the entry to our tracked list
            self.menu_entries.append(entry)

            # Get the registered top level menu
            menu = self._tool_menus.find_menu(self._top_level_menu)

            # Add the entry object to the menu
            menu.add_menu_entry_object(entry)

        except Exception as err:
            raise RuntimeError(
                "Its possible unreal hasn't loaded yet. Here's the "
                "error that occurred: {err}".format(err=err)
            )
