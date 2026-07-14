import time

from qtpy import QtCore
from qtpy.QtWidgets import QAction, QStyle
from qtpy.QtCore import Qt

from ayon_core.ui.components.buttons import AYButton
from ayon_core.ui.components.check_box import AYCheckBox
from ayon_core.ui.components.combo_box import AYComboBox
from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.label import AYLabel
from ayon_core.ui.components.layouts import AYHBoxLayout, AYVBoxLayout
from ayon_core.ui.components.option_action import AYMenu, AYOptionalAction
from ayon_core.ui.components.text_box import AYTextBox
from ayon_core.ui.components.user_image import AYUserImage
from ayon_core.ui.drawers import get_icon, enum_to_str
from ayon_core.ui.preview.constants import EXAMPLE_STATUSES
from ayon_core.ui.preview.utils import (
    Style,
    preview_widget,
    get_test_data_dir,
)
from ayon_core.ui.style_types import StyleData
from ayon_core.ui.variants import QPushButtonVariants


def _enum_values(enum):
    # qmeta = QtCore.QMetaEnum(enum)
    meta_object: QtCore.QMetaObject = QStyle.staticMetaObject  # type: ignore
    enum_index = meta_object.indexOfEnumerator(enum.__name__)
    meta_enum: QtCore.QMetaEnum = meta_object.enumerator(enum_index)
    num_keys = meta_enum.keyCount()
    vals = [meta_enum.value(v) for v in range(num_keys) if
            meta_enum.key(v)]
    # print(f"=== enum = {meta_enum.scope()}.{meta_enum.enumName()} -> {keys}")
    return vals


def _setup_context_menu(widget):
    def _make_icon(name):
        return get_icon(
            name, color="#f2f2f3", color_disabled="#727273", fill=False
        )

    menu = AYMenu(parent=widget)
    copy_icon = _make_icon("content_copy")
    one_icon = _make_icon("counter_1")
    two_icon = _make_icon("counter_2")
    pin_icon = _make_icon("pin")
    block_icon = _make_icon("block")
    danger_icon = _make_icon("delete")
    # text only
    menu.addAction("Text only")

    # icon + shortcut
    a2 = QAction(copy_icon, "Icon + shortcut", parent=menu)
    a2.setShortcut("Ctrl+C")
    menu.addAction(a2)

    menu.addSeparator()

    # icon and sub-menu
    a3 = AYMenu("Sub-menu", parent=menu)
    a3.setIcon(pin_icon)

    # radio group actions
    a3.addAction(one_icon, "Sub-action 1", "Ctrl+1")
    a3.addAction(two_icon, "Sub-action 2", "Ctrl+2")
    subsub = AYMenu("Sub-sub-menu", parent=a3)
    subsub.addAction("Sub-sub-action 1")
    subsub.addAction("Sub-sub-action 2")
    a3.addMenu(subsub)
    menu.addMenu(a3)
    menu.addSeparator()

    # checkable action
    a4 = QAction("Checkable action", menu)
    a4.setShortcut("Backspace")
    a4.setCheckable(True)
    menu.addAction(a4)

    menu.addSeparator()

    # optional action (with option box)
    a5 = AYOptionalAction(
        "Optional action",
        parent=menu,
    )
    a5.option_clicked.connect(
        lambda: print("'Optional action' option clicked")
    )
    a5.triggered.connect(lambda: print("'Optional action' clicked"))
    menu.addAction(a5)

    a5a = AYOptionalAction(
        "Optional action with icon",
        icon_name="save",
        parent=menu,
    )
    a5a.option_clicked.connect(
        lambda: print("'Optional action with icon' option clicked")
    )
    a5a.triggered.connect(
        lambda: print("'Optional action with icon' clicked")
    )
    menu.addAction(a5a)

    a5b = AYOptionalAction(
        "Optional action with icon disabled",
        icon_name="save",
        parent=menu,
    )
    a5b.setEnabled(False)
    a5b.option_clicked.connect(
        lambda: print(
            "'Optional action with icon disabled' option clicked"
        )
    )
    a5b.triggered.connect(
        lambda: print("'Optional action with icon disabled' clicked")
    )
    menu.addAction(a5b)

    menu.addSeparator()

    # disabled action
    a6 = QAction(block_icon, "Disabled action", menu)
    a6.setEnabled(False)
    menu.addAction(a6)

    # dangerous action
    a7 = QAction(danger_icon, "Dangerous action", menu)
    a7.setShortcut("Ctrl+D")
    a7.setProperty("variant", "danger")
    menu.addAction(a7)

    # enable context menu on the widget
    widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    widget.customContextMenuRequested.connect(
        lambda pos: menu.exec_(widget.mapToGlobal(pos))
    )


def time_it(func):
    i = time.time()
    r = func()
    e = (time.time() - i) * 1000
    return r, e


m, e = time_it(StyleData)
print(f"  init time: {e:.6f} ms")

print("> button-surface-base: -------------------------------------------")
d, e = time_it(lambda: m.get_style("QPushButton", "surface", "base"))
print(f"  style time: {e:.6f} ms")

print("> button-surface-hover -------------------------------------------")
d, e = time_it(lambda: m.get_style("QPushButton", "surface", "hover"))
print(f"  style time: {e:.6f} ms")

d, e = time_it(lambda: m.get_style("QPushButton", "surface", "hover"))
print(f"  cached style time: {e:.6f} ms")

m.dump_cache_stats()

print("> enum_to_str benchmarking --------------------------------------")
ee = 0
i = 0
s = ""
vals = _enum_values(QStyle.ControlElement)
for i, v in enumerate(vals):
    s, e = time_it(lambda: enum_to_str(QStyle.ControlElement, v, ""))
    ee += e
ee /= i
print(f"  enum_to_str = {s!r}: {ee:.6f} ms ({i} lookups)")
s = ""
ee = 0
runs = 1000
for i in range(runs):
    for i, v in enumerate(vals):
        s, e = time_it(
            lambda: enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_PushButtonBevel,
                "",
            )
        )
        ee += e
total_runs = runs * len(vals)
ee /= total_runs
print(f"  cached enum_to_str = {s!r}: {ee:.6f} ms ({total_runs} runs)")

print("> ui test --------------------------------------------------------")


def _ui_test():
    # Create and show the test widget
    widget = AYContainer(
        layout=AYContainer.Layout.VBox,
        variant=AYContainer.Variants.Default,
        margin=0,
        layout_spacing=10,
        layout_margin=10,
    )

    container_1 = AYContainer(
        widget,
        layout=AYContainer.Layout.VBox,
        variant=AYContainer.Variants.Low,
        margin=0,
        layout_margin=10,
        layout_spacing=10,
    )
    container_1.setToolTip("container_1")
    widget.add_widget(container_1)

    variants = [v for v in QPushButtonVariants]

    # text buttons
    l1 = AYHBoxLayout(margin=0)
    for i, var in enumerate(variants):
        b = AYButton(
            f"{var.value} button",
            variant=var,
            tooltip=f"using variant {var.value}...",
        )
        l1.addWidget(b)
    container_1.add_layout(l1)

    # text + icon buttons
    l2 = AYHBoxLayout(margin=0)
    for i, var in enumerate(variants):
        b = AYButton(f"{var.value} button", variant=var, icon="add")
        l2.addWidget(b)
    container_1.add_layout(l2)

    container_2 = AYContainer(
        layout=AYContainer.Layout.HBox,
        variant=AYContainer.Variants.Low,
        margin=0,
        layout_margin=10,
        layout_spacing=10,
    )
    # icon buttons
    for i, var in enumerate(variants):
        b = AYButton(
            variant=var,
            icon="add",
            name_id="ICON_ONLY" if i == 0 else "",
        )
        container_2.add_widget(b)
    container_2.addStretch()
    widget.add_widget(container_2)

    container_3 = AYContainer(
        layout=AYContainer.Layout.HBox,
        variant=AYContainer.Variants.Low,
        margin=0,
        layout_margin=10,
        layout_spacing=10,
    )
    te = AYTextBox()
    te.set_markdown(
        "## Title\nText can be **bold** or *italic*, as expected !\n"
        "- [ ] Do this\n- [ ] Do that\n"
    )
    container_3.add_widget(te)
    vblyt = AYVBoxLayout(spacing=8)
    cbb = AYComboBox(items=EXAMPLE_STATUSES)
    vblyt.addWidget(cbb)
    cbbi = AYComboBox(items=EXAMPLE_STATUSES, inverted=True)
    vblyt.addWidget(cbbi)
    cb = AYCheckBox("CheckBox")
    cb.setToolTip(("A typical switch..."))
    vblyt.addWidget(cb)
    vblyt.addWidget(AYLabel("Normal label", tool_tip="text only"))
    vblyt.addWidget(
        AYLabel("Dimmed label", dim=True, tool_tip="text dimmed")
    )
    vblyt.addWidget(
        AYLabel(
            "Icon + text label",
            icon="favorite",
            tool_tip="Icon and text",
        )
    )
    vblyt.addWidget(
        AYLabel(
            icon="token",
            icon_color="#ff8800",
            icon_size=32,
            tool_tip="32 px orange icon only",
        )
    )
    vblyt.addWidget(
        AYLabel(
            "a badge",
            icon_color="#0088ff",
            variant=AYLabel.Variants.Badge,
            tool_tip="a blue badge",
        )
    )
    vblyt.addStretch()
    container_3.add_layout(vblyt)

    # 3rd column
    col3_lyt = AYVBoxLayout(spacing=8)
    usr_ly = AYHBoxLayout(spacing=8)
    usr_ly.addWidget(
        AYUserImage(
            src=get_test_data_dir() / "avatar1.jpg"
            if get_test_data_dir()
            else ""
        )
    )
    usr_ly.addWidget(AYUserImage(full_name="John Doe"))
    col3_lyt.addLayout(usr_ly)

    ctx_menu_label = AYLabel(
        "Right-click here for a menu",
        variant=AYLabel.Variants.Default,
        rel_text_size=2,
        icon="menu",
    )
    col3_lyt.addWidget(ctx_menu_label)
    # add a context menu to the label
    _setup_context_menu(ctx_menu_label)

    col3_lyt.addStretch()
    container_3.add_layout(col3_lyt)

    container_3.addStretch()
    widget.add_widget(container_3)

    return widget


if __name__ == "__main__":
    preview_widget(_ui_test, style=Style.AYONStyle)
