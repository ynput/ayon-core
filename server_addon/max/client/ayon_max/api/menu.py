# -*- coding: utf-8 -*-
"""3dsmax menu definition of AYON."""
import os
from qtpy import QtWidgets, QtCore
from pymxs import runtime as rt

from ayon_core.tools.utils import host_tools
from ayon_core.hosts.max.api import lib


class AYONMenu(object):
    """Object representing AYON menu.

    This is using "hack" to inject itself before "Help" menu of 3dsmax.
    For some reason `postLoadingMenus` event doesn't fire, and main menu
    if probably re-initialized by menu templates, se we wait for at least
    1 event Qt event loop before trying to insert.

    """

    def __init__(self):
        super().__init__()
        self.main_widget = self.get_main_widget()
        self.menu = None

        timer = QtCore.QTimer()
        # set number of event loops to wait.
        timer.setInterval(1)
        timer.timeout.connect(self._on_timer)
        timer.start()

        self._timer = timer
        self._counter = 0

    def _on_timer(self):
        if self._counter < 1:
            self._counter += 1
            return

        self._counter = 0
        self._timer.stop()
        self._build_ayon_menu()

    @staticmethod
    def get_main_widget():
        """Get 3dsmax main window."""
        return QtWidgets.QWidget.find(rt.windows.getMAXHWND())

    def get_main_menubar(self) -> QtWidgets.QMenuBar:
        """Get main Menubar by 3dsmax main window."""
        return list(self.main_widget.findChildren(QtWidgets.QMenuBar))[0]

    def _get_or_create_ayon_menu(
            self, name: str = "&AYON",
            before: str = "&Help") -> QtWidgets.QAction:
        """Create AYON menu.

        Args:
            name (str, Optional): AYON menu name.
            before (str, Optional): Name of the 3dsmax main menu item to
                add AYON menu before.

        Returns:
            QtWidgets.QAction: AYON menu action.

        """
        if self.menu is not None:
            return self.menu

        menu_bar = self.get_main_menubar()
        menu_items = menu_bar.findChildren(
            QtWidgets.QMenu, options=QtCore.Qt.FindDirectChildrenOnly)
        help_action = None
        for item in menu_items:
            if name in item.title():
                # we already have AYON menu
                return item

            if before in item.title():
                help_action = item.menuAction()
        tab_menu_label = os.environ.get("AYON_MENU_LABEL") or "AYON"
        op_menu = QtWidgets.QMenu("&{}".format(tab_menu_label))
        menu_bar.insertMenu(help_action, op_menu)

        self.menu = op_menu
        return op_menu

    def _build_ayon_menu(self) -> QtWidgets.QAction:
        """Build items in AYON menu."""
        ayon_menu = self._get_or_create_ayon_menu()
        load_action = QtWidgets.QAction("Load...", ayon_menu)
        load_action.triggered.connect(self.load_callback)
        ayon_menu.addAction(load_action)

        publish_action = QtWidgets.QAction("Publish...", ayon_menu)
        publish_action.triggered.connect(self.publish_callback)
        ayon_menu.addAction(publish_action)

        manage_action = QtWidgets.QAction("Manage...", ayon_menu)
        manage_action.triggered.connect(self.manage_callback)
        ayon_menu.addAction(manage_action)

        library_action = QtWidgets.QAction("Library...", ayon_menu)
        library_action.triggered.connect(self.library_callback)
        ayon_menu.addAction(library_action)

        ayon_menu.addSeparator()

        workfiles_action = QtWidgets.QAction("Work Files...", ayon_menu)
        workfiles_action.triggered.connect(self.workfiles_callback)
        ayon_menu.addAction(workfiles_action)

        ayon_menu.addSeparator()

        res_action = QtWidgets.QAction("Set Resolution", ayon_menu)
        res_action.triggered.connect(self.resolution_callback)
        ayon_menu.addAction(res_action)

        frame_action = QtWidgets.QAction("Set Frame Range", ayon_menu)
        frame_action.triggered.connect(self.frame_range_callback)
        ayon_menu.addAction(frame_action)

        colorspace_action = QtWidgets.QAction("Set Colorspace", ayon_menu)
        colorspace_action.triggered.connect(self.colorspace_callback)
        ayon_menu.addAction(colorspace_action)

        unit_scale_action = QtWidgets.QAction("Set Unit Scale", ayon_menu)
        unit_scale_action.triggered.connect(self.unit_scale_callback)
        ayon_menu.addAction(unit_scale_action)

        return ayon_menu

    def load_callback(self):
        """Callback to show Loader tool."""
        host_tools.show_loader(parent=self.main_widget)

    def publish_callback(self):
        """Callback to show Publisher tool."""
        host_tools.show_publisher(parent=self.main_widget)

    def manage_callback(self):
        """Callback to show Scene Manager/Inventory tool."""
        host_tools.show_scene_inventory(parent=self.main_widget)

    def library_callback(self):
        """Callback to show Library Loader tool."""
        host_tools.show_library_loader(parent=self.main_widget)

    def workfiles_callback(self):
        """Callback to show Workfiles tool."""
        host_tools.show_workfiles(parent=self.main_widget)

    def resolution_callback(self):
        """Callback to reset scene resolution"""
        return lib.reset_scene_resolution()

    def frame_range_callback(self):
        """Callback to reset frame range"""
        return lib.reset_frame_range()

    def colorspace_callback(self):
        """Callback to reset colorspace"""
        return lib.reset_colorspace()

    def unit_scale_callback(self):
        """Callback to reset unit scale"""
        return lib.reset_unit_scale()
