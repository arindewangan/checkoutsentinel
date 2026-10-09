"""Intervention policy engine: risk tier + context -> autonomous action.

The policy is deliberately explicit and auditable: merchants see *why* each
intervention fired. In Stage II this table is extended with a learned policy
(the LLM agent may propose overrides, which are logged and require the same
audit fields).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Intervention:
    action: str      # ALLOW | SOFT_REVIEW | STEP_UP_AUTH | RESCUE_OFFER | MANUAL_REVIEW | HOLD_CAPTURE
    priority: str    # P1 | P2 | P3 | none
    detail: str
    rescue_code: str | None = None  # simulated discount code, demo only


RESCUE_DISCOUNT_PCT = 10  # demo constant; merchant-configurable in production


def decide(txn: dict, tier: str, score: int, signals: list) -> Intervention:
    event = txn.get("event", "payment_attempt")
    prior_orders = int(txn.get("prior_orders") or 0)
    rescue_eligible = prior_orders > 0 or bool(txn.get("discount_sensitive"))

    # --- cart abandonment guard (applies before risk tiering) ---
    if event == "abandoned":
        if tier in ("LOW", "MEDIUM"):
            return Intervention(
                action="RESCUE_OFFER", priority="P3",
                detail=(f"Low-risk abandoned cart (${float(txn.get('amount', 0)):.2f}). "
                        f"Autonomous win-back: simulated {RESCUE_DISCOUNT_PCT}% code issued."),
                rescue_code=f"SENTINEL-{RESCUE_DISCOUNT_PCT}OFF-DEMO",
            )
        return Intervention(
            action="MANUAL_REVIEW", priority="P2",
            detail=f"Abandoned cart with {tier} risk ({score}) — held for review, no rescue code issued.",
        )

    # --- payment-attempt policy ---
    if tier == "CRITICAL":
        return Intervention(
            action="HOLD_CAPTURE", priority="P1",
            detail=(f"CRITICAL risk ({score}). Capture held; routed to manual review queue. "
                    "Customer sees a polite 'additional verification' message."),
        )
    if tier == "HIGH":
        if rescue_eligible:
            return Intervention(
                action="STEP_UP_AUTH", priority="P2",
                detail=(f"HIGH risk ({score}) on a returning/discount-sensitive shopper. "
                        "Step-up authentication (3-D Secure) required before capture; "
                        f"a simulated {RESCUE_DISCOUNT_PCT}% rescue incentive is offered on success "
                        "to protect conversion."),
                rescue_code=f"SENTINEL-{RESCUE_DISCOUNT_PCT}OFF-DEMO",
            )
        return Intervention(
            action="STEP_UP_AUTH", priority="P2",
            detail=(f"HIGH risk ({score}). Step-up authentication required before capture; "
                    "case mirrored to the manual review queue."),
        )
    if tier == "MEDIUM":
        return Intervention(
            action="SOFT_REVIEW", priority="P3",
            detail=(f"MEDIUM risk ({score}). Payment auto-approved to protect conversion; "
                    "transaction flagged for asynchronous analyst review."),
        )
    return Intervention(
        action="ALLOW", priority="none",
        detail=f"LOW risk ({score}). Auto-approved, no friction added.",
    )
