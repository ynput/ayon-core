import os
import sys

from qtpy import QtWidgets, QtCore, QtGui

from ayon_core.tools.utils import host_tools
from ayon_core.pipeline import registered_host
from ayon_core.style import load_stylesheet
from ayon_core.resources import get_ayon_icon_filepath

MENU_LABEL = os.environ["AYON_MENU_LABEL"]


class Spacer(QtWidgets.QWidget):
    def __init__(self, height, *args, **kwargs):
        super(Spacer, self).__init__(*args, **kwargs)

        self.setFixedHeight(height)

        real_spacer = QtWidgets.QWidget(self)
        real_spacer.setObjectName("Spacer")
        real_spacer.setFixedHeight(height)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(real_spacer)

        self.setLayout(layout)


class AYONMenu(QtWidgets.QWidget):
    def __init__(self, *args, **kwargs):
        super(AYONMenu, self).__init__(*args, **kwargs)

        self.setObjectName(f"{MENU_LABEL}Menu")

        icon_path = get_ayon_icon_filepath()
        icon = QtGui.QIcon(icon_path)
        self.setWindowIcon(icon)

        self.setWindowFlags(
            QtCore.Qt.Window
            | QtCore.Qt.CustomizeWindowHint
            | QtCore.Qt.WindowTitleHint
            | QtCore.Qt.WindowMinimizeButtonHint
            | QtCore.Qt.WindowCloseButtonHint
            | QtCore.Qt.WindowStaysOnTopHint
        )

        self.setWindowTitle(f"{MENU_LABEL}")
        save_current_btn = QtWidgets.QPushButton("Save current file", self)
        workfiles_btn = QtWidgets.QPushButton("Workfiles ...", self)
        create_btn = QtWidgets.QPushButton("Create ...", self)
        publish_btn = QtWidgets.QPushButton("Publish...", self)
        load_btn = QtWidgets.QPushButton("Load ...", self)
        inventory_btn = QtWidgets.QPushButton("Manage...", self)
        libload_btn = QtWidgets.QPushButton("Library...", self)

        # set_colorspace_btn = QtWidgets.QPushButton(
        #     "Set colorspace from presets", self
        # )
        # reset_resolution_btn = QtWidgets.QPushButton(
        #     "Set Resolution from presets", self
        # )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 20, 10, 20)

        layout.addWidget(save_current_btn)

        layout.addSpacing(15)
        layout.addWidget(workfiles_btn)

        layout.addSpacing(15)

        layout.addWidget(create_btn)
        layout.addWidget(load_btn)
        layout.addWidget(publish_btn)
        layout.addWidget(inventory_btn)

        layout.addSpacing(15)

        layout.addWidget(libload_btn)

        save_current_btn.clicked.connect(self.on_save_current_clicked)
        save_current_btn.setShortcut(QtGui.QKeySequence.Save)
        workfiles_btn.clicked.connect(self.on_workfile_clicked)
        create_btn.clicked.connect(self.on_create_clicked)
        publish_btn.clicked.connect(self.on_publish_clicked)
        load_btn.clicked.connect(self.on_load_clicked)
        inventory_btn.clicked.connect(self.on_inventory_clicked)
        libload_btn.clicked.connect(self.on_libload_clicked)

        # set_colorspace_btn.clicked.connect(self.on_set_colorspace_clicked)
        # reset_resolution_btn.clicked.connect(self.on_set_resolution_clicked)

        # Resize width, make height as small fitting as possible
        self.resize(200, 1)

    def on_save_current_clicked(self):
        host = registered_host()
        current_file = host.get_current_workfile()
        if not current_file:
            print("Current project is not saved. "
                  "Please save once first via workfiles tool.")
            host_tools.show_workfiles()
            return

        print(f"Saving current file to: {current_file}")
        host.save_workfile(current_file)

    def on_workfile_clicked(self):
        print("Clicked Workfile")
        host_tools.show_workfiles()

    def on_create_clicked(self):
        print("Clicked Create")
        host_tools.show_publisher(tab="create")

    def on_publish_clicked(self):
        print("Clicked Publish")
        host_tools.show_publisher(tab="publish")

    def on_load_clicked(self):
        print("Clicked Load")
        host_tools.show_loader(use_context=True)

    def on_inventory_clicked(self):
        print("Clicked Inventory")
        host_tools.show_scene_inventory()

    def on_libload_clicked(self):
        print("Clicked Library")
        host_tools.show_library_loader()

    def on_rename_clicked(self):
        print("Clicked Rename")

    def on_set_colorspace_clicked(self):
        print("Clicked Set Colorspace")

    def on_set_resolution_clicked(self):
        print("Clicked Set Resolution")



def launch_ayon_menu():
    app = QtWidgets.QApplication(sys.argv)

    ayon_menu = AYONMenu()

    stylesheet = load_stylesheet()
    ayon_menu.setStyleSheet(stylesheet)

    ayon_menu.show()

    sys.exit(app.exec_())
