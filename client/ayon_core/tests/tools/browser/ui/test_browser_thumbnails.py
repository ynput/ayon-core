from ayon_core.tools.browser.ui._browser_thumbnails import (
    _fit_thumbnail_size,
)


def test_thumbnail_size_fits_short_row():
    assert _fit_thumbnail_size(73, 22) == (47, 22)


def test_thumbnail_size_fits_tall_row():
    assert _fit_thumbnail_size(73, 98) == (73, 34)


def test_thumbnail_size_handles_empty_area():
    assert _fit_thumbnail_size(0, 30) == (0, 0)
