"""CheckoutSentinel — Stage I working prototype (Flask).

Simulates a live e-commerce checkout stream. Each event flows through the
agent loop:

    checkout event -> risk scorer -> intervention policy -> agent narration
                      -> SQLite store -> dashboard

DEMO MODE: all transactions are simulated; agent narration is template-based
unless an OpenAI-compatible LLM endpoint is configured via LLM_BASE_URL.
Nothing here claims to be a live model.
"""
from __future__ import annotations

import json
import os
import random
import uuid

from flask import Flask, jsonify, render_template, request

from sentinel.agent import LLMClient
from sentinel.policy import decide
from sentinel.risk import score_transaction
from sentinel.store import Store

# ---------------------------------------------------------------- simulator
FIRST = ["Aarav", "Meera", "Rohan", "Isha", "Kabir", "Ananya", "Vikram", "Priya",
         "Arjun", "Divya", "Karan", "Neha", "Aditya", "Sana", "Rahul"]
COUNTRIES = ["IN", "IN", "IN", "US", "SG", "AE", "GB", "DE"]
PRODUCTS = [("Wireless earbuds", 49.0), ("Mechanical keyboard", 129.0),
            ("Smart watch", 199.0), ("Laptop stand", 39.0), ("4K webcam", 149.0),
            ("Noise-cancelling headphones", 299.0), ("USB-C dock", 89.0),
            ("Ergonomic chair", 459.0), ("Portable SSD 1TB", 109.0),
            ("Gaming mouse", 69.0)]


class CheckoutSimulator:
    """Generates plausible checkout events, including fraud-flavored ones."""

    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)
        self.customers: dict[str, dict] = {}

    def _customer(self) -> tuple[str, dict]:
        if self.customers and self.rng.random() < 0.55:
            cid = self.rng.choice(list(self.customers))
            return cid, self.customers[cid]
        cid = f"cust_{self.rng.randint(1000, 9999)}"
        profile = {
            "name": self.rng.choice(FIRST),
            "country": self.rng.choice(COUNTRIES),
            "device": f"dev_{uuid.uuid4().hex[:8]}",
            "email": f"user{self.rng.randint(1,9999)}@example.com",
            "avg": round(self.rng.uniform(40, 220), 2),
        }
        self.customers[cid] = profile
        return cid, profile

    def next_event(self, force: str | None = None) -> dict:
        rng = self.rng
        cid, prof = self._customer()
        product, base = rng.choice(PRODUCTS)
        event = force or rng.choices(
            ["payment_attempt", "abandoned"], weights=[90, 10])[0]
        # 72% clean payment, 18% fraud-flavored payment, 10% abandonment
        kind = rng.random()
        txn: dict = {
            "txn_ref": f"txn_{uuid.uuid4().hex[:10]}",
            "event": "abandoned" if event == "abandoned" else "payment_attempt",
            "customer_id": cid,
            "product": product,
            "currency": "USD",
            "hour_local": rng.randint(0, 23),
            "country_billing": prof["country"],
            "country_ip": prof["country"],
            "device_id": prof["device"],
            "email": prof["email"],
            "new_payment_method": False,
            "cvv_retries": 0,
            "coupon_count": rng.choice([0, 0, 0, 1, 2]),
            "discount_sensitive": rng.random() < 0.4,
        }
        if kind < 0.72 or event == "abandoned":
            txn["amount"] = round(base * rng.uniform(0.9, 1.3), 2)
        else:  # fraud-flavored: spike the signals
            txn["amount"] = round(base * rng.uniform(2.5, 4.0), 2)
            if rng.random() < 0.6:
                txn["country_ip"] = rng.choice([c for c in COUNTRIES if c != prof["country"]])
            if rng.random() < 0.5:
                txn["device_id"] = f"dev_{uuid.uuid4().hex[:8]}"  # unknown device
            if rng.random() < 0.4:
                txn["cvv_retries"] = rng.randint(1, 3)
            if rng.random() < 0.3:
                txn["email"] = f"temp{rng.randint(1,9999)}@mailinator.com"
            if rng.random() < 0.35:
                txn["coupon_count"] = rng.randint(3, 5)
            txn["new_payment_method"] = rng.random() < 0.5
        return txn


# ------------------------------------------------------------------- app
def create_app(store_path: str = "data/checkoutsentinel.db") -> Flask:
    app = Flask(__name__)
    app.config["STORE"] = Store(store_path)
    app.config["SIM"] = CheckoutSimulator()
    app.config["AGENT"] = LLMClient()

    def run_agent_loop(txn: dict) -> dict:
        store: Store = app.config["STORE"]
        agent: LLMClient = app.config["AGENT"]
        history = store.customer_history(txn["customer_id"])
        enriched = dict(history)
        enriched["known_device"] = True  # demo: device registry not modeled
        enriched["known_payment"] = not txn.get("new_payment_method", False)
        txn = {**txn, "prior_orders": history["prior_orders"]}
        result = score_transaction(txn, enriched)
        intervention = decide(txn, result.tier, result.score, result.signals)
        reasons = result.reason_summary()
        narration, mode = agent.narrate(
            txn, result.tier, result.score, reasons,
            intervention.action, intervention.detail)
        txn_id = store.record(
            txn, result.score, result.tier,
            json.dumps([s.__dict__ for s in result.signals]),
            intervention.action, narration, mode,
            intervention.priority, intervention.detail)
        return {
            "id": txn_id, "txn_ref": txn["txn_ref"], "event": txn["event"],
            "customer_id": txn["customer_id"], "product": txn.get("product"),
            "amount": txn["amount"], "currency": txn["currency"],
            "score": result.score, "tier": result.tier,
            "signals": [s.__dict__ for s in result.signals],
            "action": intervention.action, "priority": intervention.priority,
            "detail": intervention.detail, "rescue_code": intervention.rescue_code,
            "narration": narration, "narration_mode": mode,
        }

    app.config["RUN_LOOP"] = run_agent_loop

    @app.get("/")
    def index():
        return render_template("dashboard.html",
                               llm_configured=app.config["AGENT"].configured)

    @app.get("/api/health")
    def health():
        return jsonify({"ok": True, "service": "checkoutsentinel",
                        "demo_mode": True,
                        "llm_endpoint_configured": app.config["AGENT"].configured})

    @app.post("/api/simulate")
    def simulate():
        """Run one simulated checkout event through the full agent loop."""
        force = (request.get_json(silent=True) or {}).get("force_event")
        txn = app.config["SIM"].next_event(force=force)
        return jsonify(app.config["RUN_LOOP"](txn))

    @app.get("/api/feed")
    def feed():
        store: Store = app.config["STORE"]
        return jsonify({"transactions": store.recent(25),
                        "interventions": store.interventions_recent(25)})

    @app.get("/api/stats")
    def stats():
        return jsonify(app.config["STORE"].stats())

    return app


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5057"))
    create_app().run(host="0.0.0.0", port=port, debug=False)
