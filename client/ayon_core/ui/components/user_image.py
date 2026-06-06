from __future__ import annotations

import logging
from functools import partial
from pathlib import Path
from typing import Callable

from qtpy import QtCore, QtGui, QtWidgets

from ..image_cache import ImageCache
from ..style import get_ayon_style
from ..variants import AYUserImageVariants
from .style_mixin import StyleMixin

log = logging.getLogger(__name__)


class AYUserImage(StyleMixin, QtWidgets.QLabel):
    Variants = AYUserImageVariants

    def __init__(
        self,
        *args,
        src: Path | str = "",
        name: str = "",
        full_name: str = "",
        size: int = 30,
        highlight: bool = False,
        outline: bool = True,
        file_cacher: Callable | None = None,
        variant=Variants.Default,
        **kwargs,
    ):
        # file path to icon
        self._src = src
        # short user name
        self._name = name
        # full user name
        self._full_name = full_name
        # pixmap size
        self._size = size
        # green outline if true, light grey otherwise
        self._highlight = highlight
        # enable / disable outline
        self._outline = outline
        # a file loader function for the image cache: src is the cache key.
        self._file_cacher = file_cacher
        # Variant string for looking up style data
        self._variant_str = variant.value

        super().__init__(*args, **kwargs)
        stl = get_ayon_style()
        self.setStyle(stl)
        self._style = stl.model.get_style(
            "AYUserImage", variant=self._variant_str
        )
        self._style.set_context(self)

        self.set_image()

    def _get_colors(
        self,
    ) -> tuple[QtGui.QColor, QtGui.QColor, QtGui.QColor, QtGui.QColor]:
        """Read image colors from the AYUserImage style data.

        Returns:
            A tuple of (initials_bg, outline_color, highlight_color).
        """
        style = self._style
        fg = QtGui.QColor(style.get("initials-color", "#ffffff"))
        bg = QtGui.QColor(style.get("initials-background-color", "#484875"))
        outline = QtGui.QColor(style.get("outline-color", "#e1e1e1"))
        highlight = QtGui.QColor(style.get("highlight-color", "#6be1ac"))
        return fg, bg, outline, highlight

    def set_image(self) -> None:
        """Render the user avatar pixmap and assign it to this label."""
        fg_color, bg_color, outline_color, highlight_color = self._get_colors()
        active_outline = highlight_color if self._highlight else outline_color

        dpr = self.devicePixelRatioF()
        dpr_size = int(self._size * dpr)
        has_outline = self._outline or self._highlight
        line_width = 1 if has_outline else 0
        half_line = line_width / 2

        self.pxm = QtGui.QPixmap(dpr_size, dpr_size)
        self.pxm.setDevicePixelRatio(dpr)
        self.pxm.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(self.pxm)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setFont(self.font())

        if self._src:
            if not Path(str(self._src)).exists() and self._file_cacher:
                ic = ImageCache.get_instance()
                self._src = ic.get(
                    str(self._src), partial(self._file_cacher, self._src)
                )

            # Load and draw src icon file in a circle
            source_pixmap = QtGui.QPixmap(self._src)
            source_pixmap.setDevicePixelRatio(dpr)
            if not source_pixmap.isNull():
                # Scale the source image to fit within the circle (with some
                # margin for outline)

                # Leave space for outline
                inner_size = int(dpr_size - line_width)
                scaled_pixmap = source_pixmap.scaled(
                    inner_size,
                    inner_size,
                    QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )

                # Create circular clipping path
                clip_path = QtGui.QPainterPath()
                clip_path.addEllipse(0, 0, self._size, self._size)
                painter.setClipPath(clip_path)

                # Draw the scaled image centered
                x = (dpr_size - scaled_pixmap.width()) // 2
                y = (dpr_size - scaled_pixmap.height()) // 2
                painter.drawPixmap(x, y, scaled_pixmap)

                # Reset clipping
                painter.setClipping(False)
            else:
                log.warning("Could not load src %s", self._src)
        else:
            initials = "?"
            if self._full_name:
                initials = "".join([p[0] for p in self._full_name.split()])
            elif self._name:
                initials = self._name[0]

            # Draw a circle with white initials over a color background

            # Fill circle with background color from style
            painter.setBrush(QtGui.QBrush(bg_color))
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.drawEllipse(0, 0, self._size, self._size)

            # Draw white initials
            painter.setPen(QtGui.QPen(fg_color))
            font = painter.font()
            pt_size = max(8, self._size // 2 - 3)
            font.setPointSizeF(pt_size)
            painter.setFont(font)

            painter.drawText(
                QtCore.QRect(0, 0, self._size, self._size),
                QtCore.Qt.AlignmentFlag.AlignCenter,
                initials.upper(),
            )

        # Draw outline
        if has_outline:
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.setPen(QtGui.QPen(active_outline, line_width))
            painter.drawEllipse(
                QtCore.QRectF(
                    half_line,
                    half_line,
                    self._size - line_width,
                    self._size - line_width,
                )
            )

        painter.end()

        # Set the pixmap to the label
        self.setPixmap(self.pxm)

    def update_params(self, src, full_name):
        self._src = src
        self._full_name = full_name
        self.set_image()


if __name__ == "__main__":
    from ..tester import Style, test
    from .container import AYContainer
    from .. import _get_test_data_dir

    def resource_loader(key):
        rsrc_dir = _get_test_data_dir()
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

    test(build, style=Style.AyonStyleOverCSS)
