"""Tests for the heuristic risk scorer (sentinel/risk.py)."""
from sentinel.risk import score_transaction, tier_for


def clean_txn(**kw):
    base = {"amount": 49.0, "device_id": "dev_abc123",
            "country_ip": "IN", "country_billing": "IN",
            "email": "shopper@example.com", "hour_local": 14,
            "cvv_retries": 0, "coupon_count": 0,
            "new_payment_method": False}
    base.update(kw)
    return base


def history(**kw):
    base = {"txns_last_10m": 0, "avg_amount": 55.0, "known_device": True,
            "known_payment": True, "prior_orders": 4}
    base.update(kw)
    return base


def test_clean_transaction_scores_low():
    r = score_transaction(clean_txn(), history())
    assert r.tier == "LOW" and r.score < 30


def test_amount_spike_adds_points():
    r = score_transaction(clean_txn(amount=220.0), history(avg_amount=55.0))
    assert any(s.name == "amount_spike" for s in r.signals)
    assert r.score >= 25


def test_velocity_escalates():
    r = score_transaction(clean_txn(), history(txns_last_10m=4))
    assert any(s.name == "velocity" and s.points == 20 for s in r.signals)


def test_geo_mismatch_adds_points():
    r = score_transaction(clean_txn(country_ip="RU"), history())
    assert any(s.name == "geo_mismatch" for s in r.signals)


def test_cvv_retries_add_points():
    r = score_transaction(clean_txn(cvv_retries=3), history())
    assert any(s.name == "cvv_retries" and s.points == 18 for s in r.signals)


def test_disposable_email_flagged():
    r = score_transaction(clean_txn(email="x@mailinator.com"), history())
    assert any(s.name == "disposable_email" for s in r.signals)


def test_stacked_signals_reach_critical():
    r = score_transaction(
        clean_txn(amount=300.0, country_ip="RU", cvv_retries=3,
                  email="x@mailinator.com", coupon_count=4,
                  device_id="dev_unknown1", new_payment_method=True),
        history(avg_amount=55.0, txns_last_10m=3, known_device=False,
                known_payment=False))
    assert r.tier == "CRITICAL" and r.score >= 80


def test_score_never_exceeds_100():
    r = score_transaction(
        clean_txn(amount=9999.0, cvv_retries=9, coupon_count=9,
                  email="x@tempmail.com", hour_local=3),
        history(avg_amount=1.0, txns_last_10m=9,
                known_device=False, known_payment=False))
    assert r.score <= 100


def test_tier_boundaries():
    assert tier_for(0) == "LOW" and tier_for(29) == "LOW"
    assert tier_for(30) == "MEDIUM" and tier_for(59) == "MEDIUM"
    assert tier_for(60) == "HIGH" and tier_for(79) == "HIGH"
    assert tier_for(80) == "CRITICAL" and tier_for(100) == "CRITICAL"
