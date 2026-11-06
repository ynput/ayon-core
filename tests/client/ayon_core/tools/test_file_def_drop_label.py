import pytest

from ayon_core.lib import FileDef


@pytest.mark.unit
def test_file_def_drop_label_default_and_serialized():
    assert FileDef("path").drop_label is None

    attr_def = FileDef("path", drop_label="Drop files or folders here or")
    assert attr_def.drop_label == "Drop files or folders here or"
    assert (
        attr_def.serialize()["drop_label"] == "Drop files or folders here or"
    )


@pytest.mark.unit
def test_drop_empty_shows_default_or_custom_label():
    qtpy = pytest.importorskip("qtpy")
    from qtpy import QtWidgets

    from ayon_core.tools.attribute_defs.files_widget import DropEmpty

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    default = DropEmpty(False, False, None, None)
    custom = DropEmpty(
        False, False, None, None, "Drop files or folders here or"
    )
    assert default._drop_label_widget.text() == "Drop files here or"
    assert (
        custom._drop_label_widget.text() == "Drop files or folders here or"
    )
    assert qtpy and app
