"""Tests for the intervention policy engine (sentinel/policy.py)."""
from sentinel.policy import decide


def txn(**kw):
    base = {"event": "payment_attempt", "amount": 49.0,
            "prior_orders": 4, "discount_sensitive": False}
    base.update(kw)
    return base


def test_low_risk_auto_allow():
    i = decide(txn(), "LOW", 12, [])
    assert i.action == "ALLOW" and i.priority == "none"


def test_medium_risk_soft_review():
    i = decide(txn(), "MEDIUM", 45, [])
    assert i.action == "SOFT_REVIEW" and i.priority == "P3"


def test_high_risk_new_customer_step_up_no_rescue():
    i = decide(txn(prior_orders=0), "HIGH", 70, [])
    assert i.action == "STEP_UP_AUTH" and i.rescue_code is None


def test_high_risk_returning_customer_gets_rescue_offer():
    i = decide(txn(prior_orders=6, discount_sensitive=True), "HIGH", 70, [])
    assert i.action == "STEP_UP_AUTH"
    assert i.rescue_code and "DEMO" in i.rescue_code


def test_critical_holds_capture():
    i = decide(txn(), "CRITICAL", 92, [])
    assert i.action == "HOLD_CAPTURE" and i.priority == "P1"


def test_abandoned_low_risk_gets_rescue():
    i = decide(txn(event="abandoned", amount=129.0), "LOW", 10, [])
    assert i.action == "RESCUE_OFFER" and i.rescue_code is not None


def test_abandoned_high_risk_no_rescue():
    i = decide(txn(event="abandoned"), "HIGH", 75, [])
    assert i.action == "MANUAL_REVIEW" and i.rescue_code is None
