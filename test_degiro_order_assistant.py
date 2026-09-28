import pytest

from degiro_order_assistant import (
    DegiroProduct,
    knockout_distance_pct,
    position_size,
    prepare_order,
    risk_per_unit,
)


def test_knockout_distance():
    assert knockout_distance_pct(100.0, 95.0) == pytest.approx(5.0)


def test_buy_risk_and_position_size():
    assert risk_per_unit("BUY", 100.0, 98.0) == pytest.approx(2.0)
    assert position_size(100.0, 2.0) == 50


def test_prepare_order_keeps_manual_confirmation():
    product = DegiroProduct(
        isin="TEST123",
        name="Example leveraged product",
        side="BUY",
        current_price=100.0,
        leverage=5.0,
        knockout_price=90.0,
    )
    draft = prepare_order(
        product,
        order_type="LIMIT",
        quantity=10,
        entry_price=100.0,
        stop_loss=98.0,
        risk_budget_eur=25.0,
    )
    assert draft.quantity == 10
    assert draft.max_risk_eur == pytest.approx(20.0)
    assert draft.knockout_distance_pct == pytest.approx(10.0)
    assert draft.requires_manual_confirmation is True


def test_buy_stop_must_be_below_entry():
    with pytest.raises(ValueError):
        risk_per_unit("BUY", 100.0, 101.0)


def test_risk_budget_rejects_oversized_order():
    product = DegiroProduct("TEST123", "Example", "BUY", 100.0, 5.0, 90.0)
    with pytest.raises(ValueError):
        prepare_order(
            product,
            order_type="LIMIT",
            quantity=20,
            entry_price=100.0,
            stop_loss=98.0,
            risk_budget_eur=25.0,
        )
