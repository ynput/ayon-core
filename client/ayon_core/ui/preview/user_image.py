from __future__ import annotations

from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.user_image import AYUserImage
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
        p = rsrc_dir / f"{key}.{ext}"
        if p.exists():
            return p
    return ""


def build():
    w = AYContainer(
        layout=AYContainer.Layout.HBox,
        margin=8,
        layout_margin=8,
        layout_spacing=4,
    )
    w.add_widget(AYUserImage(src="avatar1", file_cacher=resource_loader))
    w.add_widget(
        AYUserImage(
            src="avatar2", highlight=True, file_cacher=resource_loader
        )
    )
    w.add_widget(
        AYUserImage(
            src="avatar3", outline=False, file_cacher=resource_loader
        )
    )
    w.add_widget(AYUserImage(full_name="Oliver Cromwell"))
    w.add_widget(AYUserImage(name="Oliver"))
    w.add_widget(AYUserImage(highlight=True))
    w.add_widget(AYUserImage(name="Oliver", outline=False))
    w.add_widget(AYUserImage(name="Oliver", outline=False, highlight=True))
    w.add_widget(
        AYUserImage(
            src="avatar1",
            outline=False,
            size=60,
            file_cacher=resource_loader,
        )
    )
    w.add_widget(
        AYUserImage(
            src="avatar2",
            highlight=True,
            size=60,
            file_cacher=resource_loader,
        )
    )
    w.add_widget(AYUserImage(full_name="Oliver Cromwell", size=60))
    w.add_widget(AYUserImage(name="Oliver", outline=False, size=60))
    w.add_widget(
        AYUserImage(
            name="Milan",
            outline=False,
            size=24,
            variant=AYUserImage.Variants.Entity_Card,
        )
    )
    w.add_widget(
        AYUserImage(
            src="avatar1",
            file_cacher=resource_loader,
            name="Milan",
            outline=False,
            size=24,
            variant=AYUserImage.Variants.Entity_Card,
        )
    )
    return w


if __name__ == "__main__":

    preview_widget(build, style=Style.AYONStyleOverCSS)
