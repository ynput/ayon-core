import os

from ayon_core.pipeline import load


class CopyFilePath(load.LoaderPlugin):
    """Copy published file path to clipboard"""
    representations = {"*"}
    product_types = {"*"}

    label = "Copy File Path"
    order = 20
    icon = "clipboard"
    color = "#999999"

    def load(self, context, name=None, namespace=None, data=None):
        path = self.filepath_from_context(context)
        self.log.info("Added file path to clipboard: {0}".format(path))
        self.copy_path_to_clipboard(path)

    @staticmethod
    def copy_path_to_clipboard(path):
        from qtpy import QtWidgets

        clipboard = QtWidgets.QApplication.clipboard()
        assert clipboard, "Must have running QApplication instance"

        # Set to Clipboard
        clipboard.setText(os.path.normpath(path))
