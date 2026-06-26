from __future__ import annotations

from qtpy.QtCore import QTimer

from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.entity_thumbnail import AYEntityThumbnail
from ayon_core.ui.preview.utils import (
    Style,
    preview_widget,
    get_test_data_dir,
)


def resource_loader(key):
    rsrc_dir = get_test_data_dir()
    if rsrc_dir is None:
        return ""
    for ext in ("jpg", "png"):
        fpath = rsrc_dir / f"{key}.{ext}"
        if fpath.exists():
            return fpath
    return ""


def build_entity_thumbnail_preview_widget():
    w = AYContainer(
        layout=AYContainer.Layout.VBox,
        variant=AYContainer.Variants.Low,
        layout_margin=16,
        layout_spacing=24,
    )
    w1 = AYContainer(
        layout=AYContainer.Layout.HBox,
        variant=AYContainer.Variants.Low_Framed,
        layout_margin=24,
        layout_spacing=24,
    )
    w.add_widget(w1)
    w1.add_widget(
        AYEntityThumbnail(src="avatar1", file_cacher=resource_loader)
    )
    w1.add_widget(
        AYEntityThumbnail(src="avatar2", file_cacher=resource_loader)
    )
    w1.add_widget(
        AYEntityThumbnail(src="avatar3", file_cacher=resource_loader)
    )
    w1.add_widget(
        AYEntityThumbnail(src="avatar4", file_cacher=resource_loader)
    )
    w1.add_widget(
        AYEntityThumbnail(
            src="SMPTE_Color_Bars", file_cacher=resource_loader
        )
    )
    delayed = AYEntityThumbnail(
        src="avatar2", file_cacher=resource_loader, fade_duration=0
    )
    w1.add_widget(delayed)
    w1.add_widget(AYEntityThumbnail(file_cacher=resource_loader))

    w2 = AYContainer(
        layout=AYContainer.Layout.HBox,
        variant=AYContainer.Variants.Low_Framed,
        layout_margin=24,
        layout_spacing=24,
    )
    w.add_widget(w2)

    # Two-image composite
    w2.add_widget(
        AYEntityThumbnail(
            src="avatar1,avatar2",
            file_cacher=resource_loader,
            size=(85 * 2, 48 * 2),
        )
    )
    # Three-image composite
    w2.add_widget(
        AYEntityThumbnail(
            src="avatar1,avatar2,avatar3",
            file_cacher=resource_loader,
            size=(85 * 2, 48 * 2),
        )
    )
    # Four-image composite
    w2.add_widget(
        AYEntityThumbnail(
            src="avatar1,avatar2,avatar3,avatar4",
            file_cacher=resource_loader,
            size=(85 * 2, 48 * 2),
        )
    )
    #  too many composite
    paths = [
        "avatar1",
        "avatar2",
        "avatar3",
        "avatar4",
        "SMPTE_Color_Bars",
    ] * 10
    w2.add_widget(
        AYEntityThumbnail(
            src=",".join(paths),
            file_cacher=resource_loader,
            size=(85 * 2, 48 * 2),
        )
    )
    w2.add_widget(
        AYEntityThumbnail(
            src=",".join(paths),
            file_cacher=resource_loader,
        )
    )

    # simulate thumbnail update after some time
    delayed.set_fade_duration(1000)
    QTimer.singleShot(1500, lambda: delayed.set_thumbnail("avatar3"))
    return w


if __name__ == "__main__":
    preview_widget(
        build_entity_thumbnail_preview_widget,
        style=Style.AYONStyleOverCSS
    )
