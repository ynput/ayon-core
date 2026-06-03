from __future__ import annotations

import dataclasses
import threading
import weakref
from enum import Enum
from functools import partial
from pathlib import Path
from typing import Callable

from qtpy.QtCore import (
    QEasingCurve,
    QPointF,
    QRect,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
)
from qtpy.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPixmap,
    QPolygonF,
)
from qtpy.QtWidgets import QPushButton, QStyle, QStyleOptionButton

from ..image_cache import ImageCache
from ..style import get_ayon_style
from ..variants import QPushButtonVariants

try:
    from qtmaterialsymbols import get_icon  # type: ignore
except ImportError:
    from ..vendor.qtmaterialsymbols import get_icon


@dataclasses.dataclass
class _PendingCompositeState:
    """Tracks async resolution state for a multi-image composite.

    Attributes:
        resolved: Maps slot index to resolved path, or ``None`` if
            still loading.
        pending_count: Number of slots not yet resolved.
        total: Total number of requested slots.
    """

    resolved: dict[int, str | None]
    pending_count: int
    total: int


class AYEntityThumbnail(QPushButton):
    """A push button widget that displays a thumbnail image for an entity.

    Supports single images or comma-separated composites with automatic
    caching (sync and async), fade-in animations, and customizable
    placeholder icons.
    """

    class Variants(Enum):
        """Visual style variants for the thumbnail button."""

        Thumbnail = QPushButtonVariants.Thumbnail.value
        Entity_Card = QPushButtonVariants.Entity_Card.value

    # Minimum readable width (px) for each composite image slice.
    _MIN_SLICE_WIDTH: int = 10
    # 1-px inset applied to clip polygons to avoid overlapping the border.
    _CLIP_INSET: int = 1

    def __init__(
        self,
        src: Path | str = "",
        file_cacher: Callable[[str], Path | str] | None = None,
        async_file_cacher: (
            Callable[[str, Callable[[str], None]], None] | None
        ) = None,
        placeholder_icon: str = "image",
        placeholder_scale: float = 0.5,
        placeholder_icon_fill: bool = False,
        size: tuple[int, int] = (85, 48),
        fade_duration: int = 0,
        variant: Variants = Variants.Thumbnail,
        **kwargs,
    ):
        """A widget that displays a thumbnail image for an entity, with options
        to customize the image source, caching behavior, and size.

        Args:
            src: Initial image source (path or cache key).
            file_cacher: Synchronous callable ``(key) -> file_path`` used to
                populate ``ImageCache`` on a cache miss.  Called on the
                calling thread — **must not** block the Qt main thread.
            async_file_cacher: Non-blocking callable
                ``(key, on_loaded: Callable[[str], None]) -> None``.
                When the thumbnail is not yet cached this is invoked
                immediately and should schedule the download on a
                background thread.  Once the file is ready it must call
                ``on_loaded(file_path)`` on the main thread.  The widget
                will then call :meth:`set_thumbnail` again with the same
                key, which now resolves to the cached file.  Mutually
                exclusive with *file_cacher*.
            placeholder_icon: Icon name shown before the thumbnail loads.
            placeholder_scale: Scale factor for the placeholder icon.
            placeholder_icon_fill: Whether to fill the placeholder icon.
            size: ``(width, height)`` in pixels.
            fade_duration: Fade-in animation duration in milliseconds.
            variant: Visual style variant.

        Raises:
            ValueError: If both *file_cacher* and *async_file_cacher* are set.
        """
        self._file_cacher = file_cacher
        self._async_file_cacher: (
            Callable[[str, Callable[[str], None]], None] | None
        ) = async_file_cacher
        # Keys for which an async fetch is already in flight (avoid duplicates)
        self._pending_async_keys: set[str] = set()
        self._pending_lock = threading.Lock()
        # In-memory cache of assembled composite pixmaps keyed by the
        # original comma-separated src string.  Cleared on size changes.
        self._composite_cache: dict[str, QPixmap] = {}
        if file_cacher and async_file_cacher:
            raise ValueError(
                "Only one of 'file_cacher' or 'async_file_cacher' may be "
                "set, not both."
            )
        self._size = size
        self._variant_str: str = variant.value
        self._placeholder_icon_name = placeholder_icon
        self._placeholder_scale = placeholder_scale
        self._placeholder_icon_fill = placeholder_icon_fill
        icn_size = int(size[1] * placeholder_scale)
        self._placeholder_icon = QIcon(
            get_icon(
                placeholder_icon,
                color="#10ffffff",
                fill=placeholder_icon_fill,
            ).pixmap(
                QSize(icn_size, icn_size),
            )
        )

        super().__init__(QIcon(), "", **kwargs)
        self.setStyle(get_ayon_style())

        self._src: Path | str = ""
        self._incoming_pixmap: QPixmap | None = None
        self._opacity: float = 1.0
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(fade_duration)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._anim.valueChanged.connect(self._on_fade_tick)
        self._anim.finished.connect(self._on_fade_done)
        self._bg_color = QColor(
            get_ayon_style()
            .model.get_style("QPushButton", variant=self._variant_str)
            .get("background-color", "#000000")
        )

        self.set_thumbnail(src)
        self.setFixedSize(*self._size)

    @property
    def slant_px(self) -> int:
        """Return the horizontal slant offset in pixels for composite slices.

        This value determines how much each slice edge is skewed to create
        a diagonal separation effect between composite images. We default to
        10% of the widget's width.
        """
        return int(self._size[0] * 0.1)

    @property
    def max_slices(self) -> int:
        """Return the maximum number of slices that fit within the widget width.

        Calculated based on :attr:`_MIN_SLICE_WIDTH` to ensure each slice
        is at least the minimum readable width.
        """
        return int(self._size[0] / self._MIN_SLICE_WIDTH)

    def set_fade_duration(self, duration: int) -> None:
        """Set the duration of the fade animation when changing thumbnails.

        Args:
            duration: Animation duration in milliseconds.
        """
        self._anim.setDuration(duration)

    def set_size(self, size: tuple[int, int]) -> None:
        """Resize the thumbnail and update the icon size to match.

        Clears the in-memory composite cache since cached composites
        are size-specific.

        Args:
            size: New ``(width, height)`` in pixels.
        """
        self._size = size
        # Cached composites are size-specific; they must be rebuilt.
        self._composite_cache.clear()
        icn_size = int(size[1] * self._placeholder_scale)
        self._placeholder_icon = QIcon(
            get_icon(
                self._placeholder_icon_name,
                color="#10ffffff",
                fill=self._placeholder_icon_fill,
            ).pixmap(QSize(icn_size, icn_size))
        )
        self.setFixedSize(*self._size)
        if self.icon() and not self.icon().isNull():
            self.setIconSize(QSize(*self._size))
        self.update()

    def set_placeholder_icon(self, icon_name: str) -> None:
        """Set the placeholder icon to show when no thumbnail is available.

        Args:
            icon_name: Material symbol icon name (e.g., ``"image"``).
        """
        if not icon_name:
            return
        self._placeholder_icon_name = icon_name
        icn_size = int(self._size[1] * self._placeholder_scale)
        self._placeholder_icon = QIcon(
            get_icon(
                icon_name,
                color="#10ffffff",
                fill=self._placeholder_icon_fill,
            ).pixmap(QSize(icn_size, icn_size))
        )
        if not self.icon() or self.icon().isNull():
            self.setIcon(self._placeholder_icon)
            self.setIconSize(QSize(*self._size))
            self.update()

    def _resolve_src(self, src: Path | str) -> Path | str:
        """Resolve a cache key or path to an existing file path.

        Pure resolution — no side effects.

        Resolution order:
        1. If *src* is already a real path on disk, return it as-is.
        2. If a synchronous *file_cacher* is configured, populate
           ``ImageCache`` now (blocking) and return the cached path.
        3. If the key is already in ``ImageCache``, return its path.
        4. Fall through: return *src* unchanged (shows placeholder).

        Args:
            src: A file path, cache key, or empty string.

        Returns:
            Resolved file path if available, otherwise the original *src*.
        """
        if Path(src).exists():
            return src
        ic = ImageCache.get_instance()
        if self._file_cacher:
            return ic.get(str(src), partial(self._file_cacher, src))
        if ic.has(str(src)):
            return ic.get_path(str(src)) or ""
        return src

    def _maybe_schedule_async_fetch(self, src: Path | str) -> None:
        """Schedule a non-blocking background fetch for *src* if needed.

        Does nothing when *async_file_cacher* is not set or a fetch for
        *src* is already in flight.  On completion, calls
        :meth:`_load_pixmap_from_path` directly with the resolved path.

        Args:
            src: The cache key or path to fetch asynchronously.
        """
        if not self._async_file_cacher:
            return
        key_str = str(src)
        if not key_str or key_str in self._pending_async_keys:
            return
        self._pending_async_keys.add(key_str)
        thumbnail_ref = weakref.ref(self)

        def _on_loaded(fpath: str, _k: str = key_str) -> None:
            thumbnail = thumbnail_ref()
            if thumbnail is None:
                return
            thumbnail._pending_async_keys.discard(_k)
            if fpath:
                thumbnail._load_pixmap_from_path(fpath)

        self._async_file_cacher(key_str, _on_loaded)

    def _center_crop_pixmap(
        self,
        pixmap: QPixmap,
        slot_w: int,
        slot_h: int,
    ) -> QPixmap:
        """Scale to widget height then center-crop to slot width.

        The image is first scaled so its height equals *slot_h* (preserving
        aspect ratio).  If the resulting width exceeds *slot_w* the centre
        strip is extracted.  If it is narrower the image is centred over the
        widget background colour.

        Args:
            pixmap: Source pixmap.
            slot_w: Target width in pixels.
            slot_h: Target height in pixels.

        Returns:
            A new QPixmap of exactly (slot_w, slot_h).
        """
        scaled = pixmap.scaledToHeight(
            slot_h,
            Qt.TransformationMode.SmoothTransformation,
        )
        if scaled.width() >= slot_w:
            x = (scaled.width() - slot_w) // 2
            return scaled.copy(QRect(x, 0, slot_w, slot_h))
        # Image narrower than slot — centre on background fill.
        result = QPixmap(slot_w, slot_h)
        result.fill(self._bg_color)
        if not scaled.isNull():
            painter = QPainter(result)
            x = (slot_w - scaled.width()) // 2
            painter.drawPixmap(x, 0, scaled)
            painter.end()
        return result

    def _build_composite_pixmap(self, paths: list[str]) -> QPixmap:
        """Assemble a horizontal composite pixmap from multiple image paths.

        Each image occupies an equal-width slot and is center-cropped to
        fill it entirely.  Slots whose path is empty or unreadable are left
        as the widget background color.  When the number of images exceeds
        :attr:`max_slices`, a ``more_horiz`` icon is overlaid on the last
        slot to indicate hidden items.

        Args:
            paths: Ordered list of resolved file paths, one per slot.

        Returns:
            A composite QPixmap of ``self._size``.
        """
        w, h = self._size
        num_paths = len(paths)
        slot_w = max(w // num_paths, self._MIN_SLICE_WIDTH)
        ci = self._CLIP_INSET

        result = QPixmap(w, h)
        result.fill(self._bg_color)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        hslpx = self.slant_px // 2
        max_slices = self.max_slices
        last_i = min(num_paths, max_slices) - 1
        num_drawn = 0

        for i, path in enumerate(paths):
            if not path:
                continue
            raw = QPixmap(path)
            if raw.isNull():
                continue

            cropped = self._center_crop_pixmap(raw, slot_w + hslpx * 2, h)
            # Parallelogram clip: left edge slants right, right edge slants
            # left, creating a diagonal separation between adjacent slices.
            left_slant = hslpx if i > 0 else 0
            right_slant = hslpx if i < last_i else 0
            polygon = QPolygonF(
                [
                    QPointF(i * slot_w + left_slant + ci, ci),
                    QPointF((i + 1) * slot_w + hslpx - ci, ci),
                    QPointF(
                        (i + 1) * slot_w - right_slant - ci,
                        h - ci,
                    ),
                    QPointF(i * slot_w - hslpx + ci, h - ci),
                ]
            )
            clip_path = QPainterPath()
            clip_path.addPolygon(polygon)
            painter.setClipPath(clip_path)
            painter.drawPixmap(i * slot_w - hslpx, 0, cropped)

            num_drawn += 1
            if num_drawn >= max_slices:
                icon_size = 16
                icon_pad = 2
                overflow_icon = get_icon(
                    "more_horiz",
                    color="#f2f2f3",
                    fill=False,
                ).pixmap(QSize(icon_size, icon_size))
                painter.drawPixmap(
                    (i + 1) * slot_w - icon_size - icon_pad,
                    h - icon_size - icon_pad,
                    overflow_icon,
                )
                break

        painter.end()
        return result

    def _on_fade_tick(self, value: float) -> None:
        """Handle each step of the fade-in animation.

        Updates the current opacity value and triggers a repaint.

        Args:
            value: Current animation value between 0.0 and 1.0.
        """
        self._opacity = value
        self.update()

    def _on_fade_done(self) -> None:
        """Handle the completion of the fade-in animation.

        Promotes the incoming pixmap to the button's icon and resets
        the opacity state.
        """
        pixmap = self._incoming_pixmap
        if pixmap and not pixmap.isNull():
            icon = QIcon()
            icon.addPixmap(pixmap)
            self.setIcon(icon)
            self.setIconSize(QSize(*self._size))
        else:
            self.setIcon(QIcon())
        self._incoming_pixmap = None
        self._opacity = 1.0
        self.update()

    def _load_pixmap_from_path(self, fpath: str) -> None:
        """Load and display a pixmap directly from a resolved file path.

        Updates ``_src``, stops any running animation, scales the image,
        and starts the fade-in.  Avoids a second :meth:`_resolve_src`
        pass when the caller already holds the concrete path (e.g. the
        async fetch callback).

        Args:
            fpath: Absolute path to the image file.
        """
        self._src = fpath
        self._anim.stop()
        raw = QPixmap(fpath)
        self._incoming_pixmap = raw.scaled(
            QSize(*self._size),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._opacity = 0.0
        self._anim.start()

    def set_thumbnail(self, name: Path | str) -> None:
        """Set the thumbnail image for the button.

        *name* may be a single path/cache-key **or** a comma-separated
        list of paths/cache-keys.  When multiple items are given the images
        are loaded, center-cropped into equal-width slots and assembled into
        a single composite pixmap that is cached in memory.

        Args:
            name: Image source — a file path, cache key, or comma-separated
                combination of the two.
        """
        src_str = str(name).strip()
        parts = [p.strip() for p in src_str.split(",") if p.strip()]

        if len(parts) <= 1:
            resolved = self._resolve_src(name)
            if resolved and Path(resolved).exists():
                self._load_pixmap_from_path(str(resolved))
            else:
                self._src = name
                self._anim.stop()
                self._maybe_schedule_async_fetch(name)
                self._incoming_pixmap = None
                self._opacity = 1.0
                self.setIcon(self._placeholder_icon)
            return

        # --- Multi-source composite path ---
        self._src = src_str

        # Check the in-memory composite cache before resolving.
        if src_str in self._composite_cache:
            self._anim.stop()
            self._incoming_pixmap = self._composite_cache[src_str]
            self._opacity = 0.0
            self._anim.start()
            return

        # Resolve each source synchronously where possible.
        resolved_paths: dict[int, str | None] = {}
        missing_indices: list[int] = []
        for i, part in enumerate(parts):
            r = self._resolve_src(part)
            if r and Path(str(r)).exists():
                resolved_paths[i] = str(r)
            else:
                resolved_paths[i] = None
                missing_indices.append(i)

        non_empty_paths = [p for p in resolved_paths.values() if p]
        sparse_key = ",".join(non_empty_paths[: self.max_slices])
        if sparse_key in self._composite_cache:
            self._anim.stop()
            self._incoming_pixmap = self._composite_cache[sparse_key]
            self._opacity = 0.0
            self._anim.start()
            return

        if not missing_indices:
            # All slots ready — build and cache immediately.
            composite = self._build_composite_pixmap(non_empty_paths)
            self._composite_cache[sparse_key] = composite
            self._anim.stop()
            self._incoming_pixmap = composite
            self._opacity = 0.0
            self._anim.start()
            return

        # Some slots still need async fetching — show placeholder meanwhile.
        self._anim.stop()
        self._incoming_pixmap = None
        self._opacity = 1.0
        self.setIcon(self._placeholder_icon)

        if not self._async_file_cacher:
            return

        pending = _PendingCompositeState(
            resolved=resolved_paths,
            pending_count=len(missing_indices),
            total=len(parts),
        )
        thumbnail_ref = weakref.ref(self)

        def _make_slot_callback(
            slot_idx: int,
        ) -> Callable[[str], None]:
            def _on_slot_loaded(fpath: str) -> None:
                widget = thumbnail_ref()
                if widget is None:
                    return
                # Discard if a newer set_thumbnail replaced this src.
                if str(widget._src) != src_str:
                    return
                with widget._pending_lock:
                    pending.resolved[slot_idx] = fpath or None
                    pending.pending_count -= 1
                    if pending.pending_count > 0:
                        return
                all_paths = [
                    pending.resolved.get(j)
                    for j in range(pending.total)
                    if pending.resolved.get(j)
                ]
                composite = widget._build_composite_pixmap(all_paths)
                resolved_key = ",".join(all_paths[: widget.max_slices])
                widget._composite_cache[resolved_key] = composite
                widget._anim.stop()
                widget._incoming_pixmap = composite
                widget._opacity = 0.0
                widget._anim.start()

            return _on_slot_loaded

        for idx in missing_indices:
            self._async_file_cacher(parts[idx], _make_slot_callback(idx))

    def paintEvent(self, arg__1: QPaintEvent) -> None:
        """Override the default paint event to render the thumbnail with effects.

        Draws the styled button base using the AYON style model, then
        overlays the incoming pixmap with the current fade opacity for
        smooth transition animations.  Maintains a 1-pixel inset clip
        to prevent the image from overlapping the button border.

        Args:
            arg__1: The paint event containing the update region.
        """
        p = QPainter(self)
        option = QStyleOptionButton()
        self.initStyleOption(option)
        # override rect set by stylesheet
        size = QSize(*self._size)
        self.setFixedSize(size)
        option.rect = QRect(0, 0, size.width(), size.height())
        # draw base (current icon)
        get_ayon_style().drawControl(
            QStyle.ControlElement.CE_PushButton, option, p, self
        )
        # overlay incoming pixmap with fade opacity
        if self._incoming_pixmap and not self._incoming_pixmap.isNull():
            x = (size.width() - self._incoming_pixmap.width()) // 2
            y = (size.height() - self._incoming_pixmap.height()) // 2
            p.save()
            p.setClipRect(QRect(1, 1, size.width() - 2, size.height() - 2))
            p.setOpacity(self._opacity)
            p.fillRect(option.rect, self._bg_color)
            p.drawPixmap(x, y, self._incoming_pixmap)
            p.restore()


if __name__ == "__main__":
    from ..tester import Style, test
    from .container import AYContainer

    def resource_loader(key):
        rsrc_dir = Path(__file__).parent.parent / "resources"
        for ext in ("jpg", "png"):
            fpath = rsrc_dir / f"{key}.{ext}"
            if fpath.exists():
                # we could also resize the image here.
                return fpath
        return ""

    def build():
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

    test(build, style=Style.AyonStyleOverCSS)
