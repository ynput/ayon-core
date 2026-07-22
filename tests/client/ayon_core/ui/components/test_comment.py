"""Unit tests for AYCommentField mention markdown round-tripping."""

from __future__ import annotations

from ayon_core.ui.components.comment import AYCommentField
from ayon_core.ui.data_models import User


def _normalize_markdown(md: str) -> str:
    """Normalize markdown for stable comparisons across Qt backends."""
    return md.strip()


def _make_users() -> list[User]:
    return [
        User(
            name="joe",
            short_name="joe",
            full_name="Joe",
            email="joe@example.com",
        ),
        User(
            name="jane",
            short_name="jane",
            full_name="Jane",
            email="jane@example.com",
        ),
    ]


def test_mentions_roundtrip_storage_markdown(qtbot) -> None:
    """Storage-format mention links are preserved by set_markdown/as_markdown."""
    source = "Hello [Joe](user:joe) and [Jane](user:jane)"
    field = AYCommentField(text=source, user_list=_make_users())
    qtbot.addWidget(field)

    assert _normalize_markdown(field.as_markdown()) == source


def test_nested_mention_is_normalized_to_canonical_storage(qtbot) -> None:
    """Malformed nested mention links are flattened on markdown export."""
    source = "[[Joe](user:joe) 1234](user:joe)"
    field = AYCommentField(text=source, user_list=_make_users())
    qtbot.addWidget(field)

    assert _normalize_markdown(field.as_markdown()) == "[Joe](user:joe) 1234"


def test_display_format_mention_roundtrips_back_to_storage(qtbot) -> None:
    """Display-format mention links are converted back to canonical storage."""
    source = "[@Joe](user:joe)"
    field = AYCommentField(text=source, user_list=_make_users())
    qtbot.addWidget(field)

    assert _normalize_markdown(field.as_markdown()) == "[Joe](user:joe)"
