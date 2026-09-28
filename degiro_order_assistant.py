"""Standalone DEGIRO order-preparation logic for Bob.

This module deliberately does not place, submit, or automate real orders.
It converts an already selected trade setup into a reviewable order draft
and rejects stale, implausible or insufficiently protected inputs.
"""

from dataclasses import dataclass
from typing import Literal, Optional

OrderSide = Literal["BUY", "SELL"]
OrderType = Literal["MARKET", "LIMIT", "STOP_LOSS", "STOP_LIMIT"]


@dataclass(frozen=True)
class DegiroProduct:
    isin: str
    name: str
    side: OrderSide
    current_price: float
    leverage: Optional[float]
    knockout_price: Optional[float]
    currency: str = "EUR"
    spread_pct: Optional[float] = None
    liquidity_score: Optional[float] = None
    data_age_seconds: Optional[int] = None
    multiplier: float = 1.0


@dataclass(frozen=True)
class OrderDraft:
    isin: str
    product_name: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    entry_price: Optional[float]
    stop_loss: Optional[float]
    knockout_price: Optional[float]
    knockout_distance_pct: Optional[float]
    max_risk_eur: Optional[float]
    leverage: Optional[float]
    spread_pct: Optional[float]
    liquidity_score: Optional[float]
    data_age_seconds: Optional[int]
    multiplier: float
    currency: str
    requires_manual_confirmation: bool = True
    frozen: bool = True


def _validate_isin(isin: str) -> None:
    if len(isin) != 12 or not isin[:2].isalpha() or not isin[2:].isalnum():
        raise ValueError("ISIN must contain 12 alphanumeric characters with a 2-letter country prefix")
    digits = []
    for char in isin:
        if char.isdigit():
            digits.append(char)
        else:
            digits.extend(str(ord(char.upper()) - 55))
    expanded = "".join(digits)
    if len(expanded) != 13:
        raise ValueError("Invalid ISIN")
    total = 0
    for index, char in enumerate(expanded):
        value = int(char)
        if (len(expanded) - index) % 2 == 0:
            value *= 2
        total += value // 10 + value % 10
    if total % 10 != 1:
        raise ValueError("Invalid ISIN checksum")


def knockout_distance_pct(current_price: float, knockout_price: float) -> float:
    """Return absolute percentage distance from current price to KO level."""
    if current_price <= 0 or knockout_price <= 0:
        raise ValueError("Prices must be positive")
    return abs(current_price - knockout_price) / current_price * 100.0


def risk_per_unit(
    side: OrderSide,
    entry_price: float,
    stop_loss: float,
    multiplier: float = 1.0,
) -> float:
    """Return EUR-equivalent price risk per unit and validate stop direction."""
    if entry_price <= 0 or stop_loss <= 0 or multiplier <= 0:
        raise ValueError("Entry, stop-loss and multiplier must be positive")
    if side == "BUY" and stop_loss >= entry_price:
        raise ValueError("For BUY, stop-loss must be below entry")
    if side == "SELL" and stop_loss <= entry_price:
        raise ValueError("For SELL, stop-loss must be above entry")
    return abs(entry_price - stop_loss) * multiplier


def position_size(risk_budget_eur: float, risk_per_unit_eur: float) -> int:
    """Return the largest whole-unit position within the risk budget."""
    if risk_budget_eur <= 0 or risk_per_unit_eur <= 0:
        raise ValueError("Risk budget and unit risk must be positive")
    return int(risk_budget_eur // risk_per_unit_eur)


def validate_product(
    product: DegiroProduct,
    *,
    max_spread_pct: float = 1.0,
    min_liquidity_score: float = 0.0,
    max_data_age_seconds: int = 30,
    min_ko_distance_pct: float = 0.0,
) -> None:
    """Reject a product when identity, data freshness or market-quality checks fail."""
    _validate_isin(product.isin)
    if not product.name.strip():
        raise ValueError("Product name must not be empty")
    if product.side not in ("BUY", "SELL"):
        raise ValueError("Invalid order side")
    if product.currency != "EUR":
        raise ValueError("Only EUR-denominated products are supported by this draft")
    if product.current_price <= 0:
        raise ValueError("Current price must be positive")
    if product.leverage is not None and product.leverage <= 0:
        raise ValueError("Leverage must be positive")
    if product.multiplier <= 0:
        raise ValueError("Multiplier must be positive")
    if product.knockout_price is not None:
        if product.knockout_price <= 0:
            raise ValueError("KO price must be positive")
        if product.side == "BUY" and product.knockout_price >= product.current_price:
            raise ValueError("BUY product KO must be below current price")
        if product.side == "SELL" and product.knockout_price <= product.current_price:
            raise ValueError("SELL product KO must be above current price")
        if knockout_distance_pct(product.current_price, product.knockout_price) < min_ko_distance_pct:
            raise ValueError("KO distance is below the configured safety threshold")
    if product.spread_pct is not None:
        if product.spread_pct < 0 or product.spread_pct > max_spread_pct:
            raise ValueError("Spread exceeds the configured maximum")
    if product.liquidity_score is not None and product.liquidity_score < min_liquidity_score:
        raise ValueError("Liquidity is below the configured minimum")
    if product.data_age_seconds is not None:
        if product.data_age_seconds < 0 or product.data_age_seconds > max_data_age_seconds:
            raise ValueError("Market data is stale")


def prepare_order(
    product: DegiroProduct,
    *,
    order_type: OrderType,
    quantity: int,
    entry_price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    risk_budget_eur: Optional[float] = None,
    max_spread_pct: float = 1.0,
    min_liquidity_score: float = 0.0,
    max_data_age_seconds: int = 30,
    min_ko_distance_pct: float = 0.0,
) -> OrderDraft:
    """Build a DEGIRO order draft for manual review only."""
    validate_product(
        product,
        max_spread_pct=max_spread_pct,
        min_liquidity_score=min_liquidity_score,
        max_data_age_seconds=max_data_age_seconds,
        min_ko_distance_pct=min_ko_distance_pct,
    )
    if quantity < 1:
        raise ValueError("Quantity must be at least 1")
    if order_type not in ("MARKET", "LIMIT", "STOP_LOSS", "STOP_LIMIT"):
        raise ValueError("Invalid order type")
    if order_type in ("LIMIT", "STOP_LIMIT") and entry_price is None:
        raise ValueError("This order type requires an entry price")
    if order_type in ("STOP_LOSS", "STOP_LIMIT") and stop_loss is None:
        raise ValueError("This order type requires a stop-loss")
    if risk_budget_eur is not None and stop_loss is None:
        raise ValueError("A risk budget requires a stop-loss")

    max_risk = None
    if stop_loss is not None:
        effective_entry = entry_price if entry_price is not None else product.current_price
        unit_risk = risk_per_unit(product.side, effective_entry, stop_loss, product.multiplier)
        max_risk = unit_risk * quantity
        if risk_budget_eur is not None and max_risk > risk_budget_eur:
            raise ValueError("Requested quantity exceeds the risk budget")

    ko_distance = None
    if product.knockout_price is not None:
        ko_distance = knockout_distance_pct(product.current_price, product.knockout_price)

    return OrderDraft(
        isin=product.isin,
        product_name=product.name,
        side=product.side,
        order_type=order_type,
        quantity=quantity,
        entry_price=entry_price,
        stop_loss=stop_loss,
        knockout_price=product.knockout_price,
        knockout_distance_pct=ko_distance,
        max_risk_eur=max_risk,
        leverage=product.leverage,
        spread_pct=product.spread_pct,
        liquidity_score=product.liquidity_score,
        data_age_seconds=product.data_age_seconds,
        multiplier=product.multiplier,
        currency=product.currency,
    )
