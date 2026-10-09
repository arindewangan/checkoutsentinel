"""End-to-end tests for the Flask app: agent loop, API, persistence."""
import pytest

from app import create_app


@pytest.fixture()
def client():
    app = create_app(store_path=":memory:")
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c, app


def test_health(client):
    c, _ = client
    r = c.get("/api/health")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True and body["demo_mode"] is True


def test_simulate_runs_full_agent_loop(client):
    c, _ = client
    r = c.post("/api/simulate", json={})
    assert r.status_code == 200
    d = r.get_json()
    for key in ("txn_ref", "score", "tier", "signals", "action",
                "narration", "narration_mode", "detail"):
        assert key in d, f"missing {key}"
    assert 0 <= d["score"] <= 100
    assert d["narration_mode"] == "template"  # no LLM endpoint in tests
    assert "SIMULATED" in d["narration"]


def test_forced_abandoned_event(client):
    c, _ = client
    r = c.post("/api/simulate", json={"force_event": "abandoned"})
    d = r.get_json()
    assert d["event"] == "abandoned"
    assert d["action"] in ("RESCUE_OFFER", "MANUAL_REVIEW")


def test_feed_and_stats_reflect_simulations(client):
    c, _ = client
    for _ in range(5):
        c.post("/api/simulate", json={})
    feed = c.get("/api/feed").get_json()
    assert len(feed["transactions"]) == 5
    assert len(feed["interventions"]) == 5
    stats = c.get("/api/stats").get_json()
    assert stats["total"] == 5
    assert sum(stats["by_tier"].values()) == 5


def test_dashboard_renders(client):
    c, _ = client
    r = c.get("/")
    assert r.status_code == 200
    assert b"CheckoutSentinel" in r.data and b"DEMO MODE" in r.data


def test_customer_history_tracks_repeat_buyers(client):
    c, app = client
    store = app.config["STORE"]
    sim = app.config["SIM"]
    sim.rng.seed(7)
    txn = sim.next_event(force="payment_attempt")
    txn["customer_id"] = "cust_repeat_1"
    for _ in range(3):
        t = dict(txn, txn_ref=f"txn_rep_{_}")
        app.config["RUN_LOOP"](t)
    h = store.customer_history("cust_repeat_1")
    assert h["prior_orders"] == 3
    assert h["txns_last_10m"] == 3
