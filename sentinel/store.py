"""SQLite persistence for the CheckoutSentinel demo.

Tables:
  transactions  - every simulated checkout event + its risk/policy outcome
  interventions - every autonomous action taken, with priority and detail
"""
from __future__ import annotations

import os
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    txn_ref TEXT NOT NULL,
    event TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL,
    score INTEGER NOT NULL,
    tier TEXT NOT NULL,
    signals_json TEXT NOT NULL,
    action TEXT NOT NULL,
    narration TEXT NOT NULL,
    narration_mode TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS interventions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    transaction_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    priority TEXT NOT NULL,
    detail TEXT NOT NULL,
    FOREIGN KEY (transaction_id) REFERENCES transactions(id)
);
"""


class Store:
    def __init__(self, path: str = ":memory:"):
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # -- writes ---------------------------------------------------------
    def record(self, txn: dict, score: int, tier: str, signals_json: str,
               action: str, narration: str, mode: str,
               intervention_priority: str, intervention_detail: str) -> int:
        cur = self.conn.execute(
            """INSERT INTO transactions
               (ts, txn_ref, event, customer_id, amount, currency, score, tier,
                signals_json, action, narration, narration_mode)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (time.time(), txn.get("txn_ref", "?"), txn.get("event", "?"),
             txn.get("customer_id", "?"), float(txn.get("amount", 0)),
             txn.get("currency", "USD"), score, tier, signals_json,
             action, narration, mode),
        )
        txn_id = cur.lastrowid
        self.conn.execute(
            """INSERT INTO interventions
               (ts, transaction_id, action, priority, detail)
               VALUES (?, ?, ?, ?, ?)""",
            (time.time(), txn_id, action, intervention_priority, intervention_detail),
        )
        self.conn.commit()
        return txn_id

    # -- reads ----------------------------------------------------------
    def customer_history(self, customer_id: str, window_s: int = 600) -> dict:
        cutoff = time.time() - window_s
        rows = self.conn.execute(
            "SELECT amount FROM transactions WHERE customer_id=? AND ts>=?",
            (customer_id, cutoff),
        ).fetchall()
        amounts = [r["amount"] for r in rows]
        total = self.conn.execute(
            "SELECT COUNT(*) c FROM transactions WHERE customer_id=?", (customer_id,)
        ).fetchone()["c"]
        return {
            "txns_last_10m": len(amounts),
            "avg_amount": sum(amounts) / len(amounts) if amounts else 0.0,
            "prior_orders": total,
        }

    def recent(self, limit: int = 25) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM transactions ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def interventions_recent(self, limit: int = 25) -> list[dict]:
        rows = self.conn.execute(
            """SELECT i.*, t.txn_ref, t.customer_id, t.amount
               FROM interventions i JOIN transactions t ON t.id = i.transaction_id
               ORDER BY i.id DESC LIMIT ?""", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        total = self.conn.execute("SELECT COUNT(*) c FROM transactions").fetchone()["c"]
        by_tier = {r["tier"]: r["c"] for r in self.conn.execute(
            "SELECT tier, COUNT(*) c FROM transactions GROUP BY tier")}
        by_action = {r["action"]: r["c"] for r in self.conn.execute(
            "SELECT action, COUNT(*) c FROM interventions GROUP BY action")}
        rescued = self.conn.execute(
            "SELECT COUNT(*) c FROM interventions WHERE action='RESCUE_OFFER'").fetchone()["c"]
        held = self.conn.execute(
            "SELECT COUNT(*) c FROM interventions WHERE action IN ('HOLD_CAPTURE','MANUAL_REVIEW')"
        ).fetchone()["c"]
        return {"total": total, "by_tier": by_tier, "by_action": by_action,
                "rescued": rescued, "held_or_review": held}
