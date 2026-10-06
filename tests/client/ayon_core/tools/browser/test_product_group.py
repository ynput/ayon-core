"""Tests for changing the product group from the Browser."""

from __future__ import annotations

from typing import Any

import pytest

from ayon_core.tools.browser.models import products as products_module
from ayon_core.tools.browser.models.products import ProductsModel


class FakeResponse:
    def __init__(self, data: Any, status_code: int = 200) -> None:
        self.data = data
        self.status_code = status_code


def _patch_permissions(
    monkeypatch: pytest.MonkeyPatch,
    user_data: dict[str, Any],
    response: FakeResponse,
) -> None:
    monkeypatch.setattr(
        products_module.ayon_api, "get_user", lambda: {"data": user_data}
    )
    monkeypatch.setattr(
        products_module.ayon_api, "get", lambda *_args, **_kwargs: response
    )


@pytest.mark.parametrize(
    "user_data, response, expected",
    [
        # Admins, managers and services are never restricted
        ({"isAdmin": True}, FakeResponse(None, 500), True),
        ({"isManager": True}, FakeResponse(None, 500), True),
        ({"isService": True}, FakeResponse(None, 500), True),
        # Attribute writing is not restricted
        ({}, FakeResponse({"attrib_write": {"enabled": False}}), True),
        # Attribute writing is restricted to listed attributes
        (
            {},
            FakeResponse({
                "attrib_write": {
                    "enabled": True,
                    "attributes": ["productGroup"],
                }
            }),
            True,
        ),
        (
            {},
            FakeResponse({
                "attrib_write": {"enabled": True, "attributes": ["fps"]}
            }),
            False,
        ),
        # Unknown permissions are left for the server to validate
        ({}, FakeResponse(None, 404), True),
    ],
)
def test_can_change_products_group(
    monkeypatch: pytest.MonkeyPatch,
    user_data: dict[str, Any],
    response: FakeResponse,
    expected: bool,
) -> None:
    _patch_permissions(monkeypatch, user_data, response)

    assert ProductsModel().can_change_products_group("demo") is expected


def test_get_product_groups_info(monkeypatch: pytest.MonkeyPatch) -> None:
    products = [
        {"id": "p1", "folderId": "f1", "attrib": {"productGroup": "A"}},
        {"id": "p2", "folderId": "f1", "attrib": {"productGroup": None}},
        {"id": "p3", "folderId": "f1", "attrib": {"productGroup": "B"}},
        {"id": "p4", "folderId": "f2", "attrib": {"productGroup": "C"}},
    ]

    def get_products(
        _project_name: str,
        product_ids: set[str] | None = None,
        folder_ids: set[str] | None = None,
        **_kwargs: Any,
    ) -> list[dict[str, Any]]:
        return [
            product
            for product in products
            if (product_ids is None or product["id"] in product_ids)
            and (folder_ids is None or product["folderId"] in folder_ids)
        ]

    monkeypatch.setattr(
        products_module.ayon_api, "get_products", get_products
    )

    info = ProductsModel().get_product_groups_info("demo", {"p1", "p2"})

    assert info.selected == {"A"}
    assert info.available == {"A", "B"}


def test_change_products_group_ungroups_with_empty_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updates: list[tuple[Any, ...]] = []

    class FakeSession:
        def update_entity(self, *args: Any) -> None:
            updates.append(args)

        def commit(self) -> None:
            updates.append(("commit",))

    monkeypatch.setattr(products_module, "OperationsSession", FakeSession)

    ProductsModel().change_products_group("demo", {"p1"}, "")

    assert updates == [
        ("demo", "product", "p1", {"attrib": {"productGroup": None}}),
        ("commit",),
    ]


def test_change_products_group_emits_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ayon_core.tools.browser.control import BrowserController

    monkeypatch.setattr(
        ProductsModel, "change_products_group", lambda *_args: None
    )
    controller = BrowserController()
    events: list[dict[str, Any]] = []

    def on_group_changed(event: Any) -> None:
        events.append(dict(event.data))

    controller.register_event_callback(
        "products.group.changed", on_group_changed
    )

    controller.change_products_group("demo", {"p1"}, "A")

    assert events == [
        {"project_name": "demo", "product_ids": {"p1"}, "group_name": "A"}
    ]


def test_can_change_products_group_is_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def get(url: str, **_kwargs: Any) -> FakeResponse:
        calls.append(url)
        return FakeResponse({"attrib_write": {"enabled": False}})

    monkeypatch.setattr(
        products_module.ayon_api, "get_user", lambda: {"data": {}}
    )
    monkeypatch.setattr(products_module.ayon_api, "get", get)
    model = ProductsModel()

    assert model.can_change_products_group("demo") is True
    assert model.can_change_products_group("demo") is True
    assert len(calls) == 1

    # Each project has its own permissions
    model.can_change_products_group("other")
    assert len(calls) == 2

    model.reset()
    model.can_change_products_group("demo")
    assert len(calls) == 3
