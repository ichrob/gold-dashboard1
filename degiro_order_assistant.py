"""Standalone DEGIRO order-preparation logic for Bob.

This module deliberately does not place, submit, or automate real orders.
It converts an already selected trade setup into a reviewable order draft.
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
    currency: str
    requires_manual_confirmation: bool = True


def knockout_distance_pct(current_price: float, knockout_price: float) -> float:
    """Return absolute percentage distance from current price to KO level."""
    if current_price <= 0 or knockout_price <= 0:
        raise ValueError("Prices must be positive")
    return abs(current_price - knockout_price) / current_price * 100.0


def risk_per_unit(side: OrderSide, entry_price: float, stop_loss: float) -> float:
    """Return absolute price risk per unit and validate stop direction."""
    if entry_price <= 0 or stop_loss <= 0:
        raise ValueError("Entry and stop-loss must be positive")
    if side == "BUY" and stop_loss >= entry_price:
        raise ValueError("For BUY, stop-loss must be below entry")
    if side == "SELL" and stop_loss <= entry_price:
        raise ValueError("For SELL, stop-loss must be above entry")
    return abs(entry_price - stop_loss)


def position_size(risk_budget_eur: float, risk_per_unit_eur: float) -> int:
    """Return the largest whole-unit position within the risk budget."""
    if risk_budget_eur <= 0 or risk_per_unit_eur <= 0:
        raise ValueError("Risk budget and unit risk must be positive")
    return int(risk_budget_eur // risk_per_unit_eur)


def prepare_order(
    product: DegiroProduct,
    *,
    order_type: OrderType,
    quantity: int,
    entry_price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    risk_budget_eur: Optional[float] = None,
) -> OrderDraft:
    """Build a DEGIRO order draft for manual review only."""
    if quantity < 1:
        raise ValueError("Quantity must be at least 1")

    unit_risk = None
    max_risk = None
    if stop_loss is not None:
        effective_entry = entry_price if entry_price is not None else product.current_price
        unit_risk = risk_per_unit(product.side, effective_entry, stop_loss)
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
        currency=product.currency,
    )
