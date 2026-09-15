from __future__ import annotations

from functools import lru_cache

from qtpy.QtGui import QColor


@lru_cache(maxsize=256)
def relative_luminance(
    r: int, g: int, b: int, *_unused: object
) -> float:
    """Calculate relative luminance of a color, i.e. sRGB luminance in
    linear space.

    Args:
        r: Red component (0-255).
        g: Green component (0-255).
        b: Blue component (0-255).
        *_unused: Trailing components (e.g. alpha from
            ``QColor.toTuple()``) are accepted and ignored so callers
            can splat a 3- or 4-tuple directly.

    Returns:
        sRGB relative luminance in [0.0, 1.0].
    """
    comp = [r, g, b]
    for i in range(3):
        comp[i] /= 255
        if comp[i] <= 0.03928:
            comp[i] /= 12.92
        else:
            comp[i] = ((comp[i] + 0.055) / 1.055) ** 2.4
    return comp[0] * 0.2126 + comp[1] * 0.7152 + comp[2] * 0.0722


def contrast_ratio(lum1: float, lum2: float) -> float:
    """Calculate the contrast ratio between two relative luminance values
    per WCAG 2.1.

    The contrast ratio ranges from 1:1 (no contrast) to 21:1 (maximum,
    black vs white). WCAG recommends:
    - 4.5:1 minimum for normal text (AA)
    - 7:1 minimum for enhanced contrast (AAA)
    - 3:1 minimum for large text or UI components
    """
    if lum1 > lum2:
        return (lum1 + 0.05) / (lum2 + 0.05)
    return (lum2 + 0.05) / (lum1 + 0.05)


@lru_cache(maxsize=256)
def _compute_color_for_contrast_rgba(
    background: tuple,  # (r, g, b, a)
    foreground: tuple,  # (r, g, b, a)
    min_contrast_ratio: float = 4.5,
) -> tuple:
    """Internal cached implementation returning an immutable RGBA tuple.

    Cached separately from :func:`compute_color_for_contrast` so that
    the public function can always return a fresh :class:`QColor`
    instance — mutating the result of a cached function would otherwise
    poison the cache for subsequent identical inputs.

    Args:
        background: Background color as ``(r, g, b, a)``.
        foreground: Foreground color as ``(r, g, b, a)``.
        min_contrast_ratio: Target minimum contrast ratio.

    Returns:
        Adjusted color as an immutable ``(r, g, b, a)`` tuple.
    """
    bg_lum = relative_luminance(*background)
    fg_lum = relative_luminance(*foreground)

    # Check if already sufficient
    current_ratio = contrast_ratio(bg_lum, fg_lum)
    if current_ratio >= min_contrast_ratio:
        return tuple(foreground)

    fg_col = QColor(*foreground)

    # Get HSL components (hue, saturation preserved)
    h = fg_col.hslHueF()
    s = fg_col.hslSaturationF()
    original_l = fg_col.lightnessF()

    # Determine if we should lighten or darken based on background
    # Use luminance midpoint (0.1791 for 4.5:1 contrast with both black/white)
    should_lighten = bg_lum < 0.1791

    # Binary search for optimal lightness
    if should_lighten:
        low, high = original_l, 1.0
        # return QColor("white")
    else:
        low, high = 0.0, original_l
        # return QColor("black")

    result = QColor(
        fg_col.red(),
        fg_col.green(),
        fg_col.blue(),
        fg_col.alpha(),
    )
    original_alpha = result.alpha()

    # Binary search (8 iterations gives ~0.4% precision)
    for _ in range(8):
        mid = (low + high) * 0.5
        result.setHslF(h if h >= 0 else 0.0, s, mid)
        result.setAlpha(original_alpha)  # Preserve alpha

        test_lum = relative_luminance(*result.toRgb().toTuple())
        test_ratio = contrast_ratio(bg_lum, test_lum)

        if test_ratio >= min_contrast_ratio:
            if should_lighten:
                high = mid  # Can use darker shade
            else:
                low = mid  # Can use lighter shade
        else:
            if should_lighten:
                low = mid  # Need lighter
            else:
                high = mid  # Need darker

    # Final adjustment to ensure we meet the threshold
    final_l = high if should_lighten else low
    result.setHslF(h if h >= 0 else 0.0, s, max(0.0, min(1.0, final_l)))
    result.setAlpha(original_alpha)  # Preserve alpha
    result = result.toRgb()

    # Verify and fallback to black/white if HSL adjustment isn't enough
    final_ratio = contrast_ratio(bg_lum, relative_luminance(*result.toTuple()))
    if final_ratio < min_contrast_ratio:
        # HSL adjustment insufficient (saturated colors can't reach target)
        # Fall back to black or white
        white_ratio = 1.05 / (bg_lum + 0.05)
        black_ratio = (bg_lum + 0.05) * 20.0
        result = (
            QColor(255, 255, 255, original_alpha)
            if white_ratio > black_ratio
            else QColor(0, 0, 0, original_alpha)
        )
    return tuple(result.toTuple())


def compute_color_for_contrast(
    background: tuple,
    foreground: tuple,
    min_contrast_ratio: float = 4.5,
) -> QColor:
    """Adjust foreground color to achieve minimum contrast with background.

    Preserves the hue and saturation of the original foreground color,
    adjusting only the lightness to achieve the required contrast ratio.

    The heavy computation is memoized via
    :func:`_compute_color_for_contrast_rgba`; this wrapper always
    returns a fresh :class:`QColor` instance so callers may mutate it
    safely without poisoning the cache.

    Args:
        background: The background color as ``(r, g, b, a)``.
        foreground: The foreground color as ``(r, g, b, a)``.
        min_contrast_ratio: Target minimum contrast ratio (default 4.5).

    Returns:
        A new :class:`QColor` with adjusted lightness meeting the
        requested contrast ratio (or the original colour when contrast
        was already sufficient).
    """
    rgba = _compute_color_for_contrast_rgba(
        tuple(background), tuple(foreground), min_contrast_ratio
    )
    return QColor(*rgba)
