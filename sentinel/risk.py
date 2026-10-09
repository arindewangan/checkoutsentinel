"""Heuristic risk-scoring engine for CheckoutSentinel (pure Python, no ML).

Stage I prototype: a transparent, explainable scorer that stands in for the
fine-tuned risk head planned for Stage II. Every point added to the score is
paired with a human-readable reason, which is exactly what the agentic layer
consumes to produce its per-transaction narration.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RiskSignal:
    name: str
    points: int
    detail: str


@dataclass
class RiskResult:
    score: int
    tier: str  # LOW | MEDIUM | HIGH | CRITICAL
    signals: list[RiskSignal] = field(default_factory=list)

    def reason_summary(self) -> str:
        if not self.signals:
            return "no risk indicators"
        return "; ".join(f"{s.name} (+{s.points}: {s.detail})" for s in self.signals)


TIER_BOUNDS = ((80, "CRITICAL"), (60, "HIGH"), (30, "MEDIUM"), (0, "LOW"))

DISPOSABLE_DOMAINS = {
    "mailinator.com", "tempmail.com", "10minutemail.com", "guerrillamail.com",
    "yopmail.com", "trashmail.com",
}


def tier_for(score: int) -> str:
    for bound, tier in TIER_BOUNDS:
        if score >= bound:
            return tier
    return "LOW"


def score_transaction(txn: dict, history: dict | None = None) -> RiskResult:
    """Score a checkout transaction dict. ``history`` carries customer context:

    {"txns_last_10m": int, "avg_amount": float, "known_device": bool,
     "known_payment": bool, "prior_orders": int}
    """
    history = history or {}
    signals: list[RiskSignal] = []
    amount = float(txn.get("amount", 0.0))

    def add(name: str, points: int, detail: str) -> None:
        signals.append(RiskSignal(name, points, detail))

    # --- amount anomaly vs customer's rolling average ---
    avg = float(history.get("avg_amount") or 0.0)
    prior_orders = int(history.get("prior_orders") or 0)
    if avg > 0 and amount >= 3 * avg:
        add("amount_spike", 25, f"${amount:.2f} is >=3x customer avg ${avg:.2f}")
    elif avg > 0 and amount >= 2 * avg:
        add("amount_spike", 15, f"${amount:.2f} is >=2x customer avg ${avg:.2f}")
    elif avg > 0 and amount >= 1.5 * avg:
        add("amount_spike", 8, f"${amount:.2f} is >=1.5x customer avg ${avg:.2f}")
    if prior_orders == 0 and amount > 200:
        add("first_order_high_value", 12, f"first order is high value (${amount:.2f})")

    # --- velocity ---
    n10 = int(history.get("txns_last_10m") or 0)
    if n10 >= 3:
        add("velocity", 20, f"{n10} transactions in the last 10 minutes")
    elif n10 == 2:
        add("velocity", 10, "2 transactions in the last 10 minutes")

    # --- device / identity ---
    if txn.get("device_id") and not history.get("known_device", True):
        add("new_device", 12, f"unrecognized device {txn['device_id'][:8]}...")
    if txn.get("country_ip") and txn.get("country_billing"):
        if txn["country_ip"] != txn["country_billing"]:
            add("geo_mismatch", 15,
                f"IP country {txn['country_ip']} != billing {txn['country_billing']}")
    if txn.get("new_payment_method") or not history.get("known_payment", True):
        if prior_orders > 0:
            add("new_payment_method", 8, "payment method never used by this customer")

    email = str(txn.get("email", ""))
    domain = email.split("@")[-1].lower() if "@" in email else ""
    if domain in DISPOSABLE_DOMAINS:
        add("disposable_email", 10, f"disposable domain {domain}")

    # --- payment friction ---
    cvv = int(txn.get("cvv_retries") or 0)
    if cvv >= 2:
        add("cvv_retries", 18, f"{cvv} CVV retries on this attempt")
    elif cvv == 1:
        add("cvv_retries", 8, "1 CVV retry on this attempt")

    # --- checkout behavior ---
    coupons = int(txn.get("coupon_count") or 0)
    if coupons >= 3:
        add("coupon_stacking", 10, f"{coupons} coupons stacked at checkout")
    hour = int(txn.get("hour_local") if txn.get("hour_local") is not None else 12)
    if 0 <= hour <= 5:
        add("night_hour", 5, f"purchase at {hour:02d}:00 local time")

    score = min(100, sum(s.points for s in signals))
    return RiskResult(score=score, tier=tier_for(score), signals=signals)
