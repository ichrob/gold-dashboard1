import pytest

from degiro_order_assistant import (
    DegiroProduct,
    knockout_distance_pct,
    position_size,
    prepare_order,
    revalidate_order,
    risk_per_unit,
    validate_product,
)


def product(**overrides):
    values = dict(
        isin="DE000BAY0017",
        name="Example leveraged product",
        side="BUY",
        current_price=100.0,
        leverage=5.0,
        knockout_price=90.0,
        spread_pct=0.2,
        liquidity_score=0.8,
        data_age_seconds=5,
    )
    values.update(overrides)
    return DegiroProduct(**values)


def test_knockout_distance():
    assert knockout_distance_pct(100.0, 95.0) == pytest.approx(5.0)


def test_buy_risk_and_position_size():
    assert risk_per_unit("BUY", 100.0, 98.0) == pytest.approx(2.0)
    assert position_size(100.0, 2.0) == 50


def test_prepare_order_keeps_manual_confirmation_and_freeze():
    draft = prepare_order(
        product(),
        order_type="LIMIT",
        quantity=10,
        entry_price=100.0,
        stop_loss=98.0,
        risk_budget_eur=25.0,
    )
    assert draft.quantity == 10
    assert draft.max_risk_eur == pytest.approx(20.0)
    assert draft.knockout_distance_pct == pytest.approx(10.0)
    assert draft.reference_price == pytest.approx(100.0)
    assert draft.requires_manual_confirmation is True
    assert draft.frozen is True


def test_revalidation_accepts_unchanged_fresh_product():
    draft = prepare_order(
        product(), order_type="LIMIT", quantity=10, entry_price=100.0,
        stop_loss=98.0, risk_budget_eur=25.0,
    )
    revalidate_order(draft, product())


def test_revalidation_rejects_price_drift():
    draft = prepare_order(
        product(), order_type="LIMIT", quantity=10, entry_price=100.0,
        stop_loss=98.0, risk_budget_eur=25.0,
    )
    with pytest.raises(ValueError, match="price moved"):
        revalidate_order(draft, product(current_price=100.6))


def test_revalidation_rejects_identity_or_risk_changes():
    draft = prepare_order(
        product(), order_type="LIMIT", quantity=10, entry_price=100.0,
        stop_loss=98.0, risk_budget_eur=25.0,
    )
    with pytest.raises(ValueError, match="Product identity"):
        revalidate_order(draft, product(isin="US0378331005"))
    with pytest.raises(ValueError, match="Knockout"):
        revalidate_order(draft, product(knockout_price=89.0))
    with pytest.raises(ValueError, match="leverage"):
        revalidate_order(draft, product(leverage=6.0))


def test_revalidation_rejects_stale_or_wide_market_data():
    draft = prepare_order(
        product(), order_type="LIMIT", quantity=10, entry_price=100.0,
        stop_loss=98.0, risk_budget_eur=25.0,
    )
    with pytest.raises(ValueError, match="stale"):
        revalidate_order(draft, product(data_age_seconds=31))
    with pytest.raises(ValueError, match="Spread"):
        revalidate_order(draft, product(spread_pct=1.1))


def test_buy_stop_must_be_below_entry():
    with pytest.raises(ValueError):
        risk_per_unit("BUY", 100.0, 101.0)


def test_risk_budget_rejects_oversized_order():
    with pytest.raises(ValueError):
        prepare_order(
            product(), order_type="LIMIT", quantity=20,
            entry_price=100.0, stop_loss=98.0, risk_budget_eur=25.0,
        )


def test_isin_is_validated():
    with pytest.raises(ValueError):
        validate_product(product(isin="BAD"))


def test_stale_data_is_rejected():
    with pytest.raises(ValueError):
        validate_product(product(data_age_seconds=31))


def test_wide_spread_is_rejected():
    with pytest.raises(ValueError):
        validate_product(product(spread_pct=1.1))


def test_low_liquidity_is_rejected():
    with pytest.raises(ValueError):
        validate_product(product(liquidity_score=0.1), min_liquidity_score=0.5)


def test_small_ko_distance_is_rejected():
    with pytest.raises(ValueError):
        validate_product(product(knockout_price=99.0), min_ko_distance_pct=2.0)


def test_limit_requires_entry():
    with pytest.raises(ValueError):
        prepare_order(product(), order_type="LIMIT", quantity=1, stop_loss=98.0)


def test_stop_orders_require_stop_loss():
    with pytest.raises(ValueError):
        prepare_order(product(), order_type="STOP_LOSS", quantity=1, entry_price=100.0)
