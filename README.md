# CheckoutSentinel 🛡️

**Real-time agentic fraud + cart-abandonment guard for e-commerce checkout.**
Built for the **ASUS UGen AI League — Battlefield Thunderstorm** (Stage I).

Every checkout event runs through an agent loop — **risk scorer → intervention
policy → agent narration** — and the agent acts autonomously: step-up
authentication, discount rescue offers, or a manual-review queue, all in
milliseconds, all auditable.

> ⚠️ **DEMO MODE** — this Stage I prototype simulates checkout traffic and uses
> template-based agent narration unless an OpenAI-compatible LLM endpoint is
> configured (`LLM_BASE_URL`). Discount codes shown are simulated.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py            # http://localhost:5057
pytest -q                # 26 tests
```

Optional live-agent mode (Stage II path — any OpenAI-compatible server):

```bash
LLM_BASE_URL=http://localhost:8080 LLM_MODEL=checkoutsentinel-24b-q8 python app.py
```

## Architecture

```
checkout event (simulated stream)
        │
        ▼
┌───────────────┐   pure-Python heuristics,      ┌────────────────┐
│  risk scorer  │── explainable per-signal ───▶ │  policy engine │
│ sentinel/     │   points (0–100, 4 tiers)      │  sentinel/     │
│ risk.py       │                                │  policy.py     │
└───────────────┘                                └────────────────┘
        │                                                 │
        ▼                                                 ▼
┌───────────────────────────────────────────────────────────────┐
│ agent loop (sentinel/agent.py): LLMClient → narration          │
│  • mode="llm": OpenAI-compatible endpoint (B70, Stage II)      │
│  • mode="template": deterministic templates, always labeled    │
└───────────────────────────────────────────────────────────────┘
        │                                        │
        ▼                                        ▼
  SQLite store                          Flask dashboard (/)
  sentinel/store.py                     live feed · stats · intervention log
```

**Intervention policy** (`sentinel/policy.py`):

| Tier | Score | Action |
|---|---|---|
| LOW | 0–29 | `ALLOW` — auto-approve, zero friction |
| MEDIUM | 30–59 | `SOFT_REVIEW` — approve now, analyst flag async |
| HIGH | 60–79 | `STEP_UP_AUTH` — 3-D Secure gate; rescue offer for returning/discount-sensitive shoppers |
| CRITICAL | 80–100 | `HOLD_CAPTURE` — hold funds, P1 manual review |
| abandoned cart (LOW/MED) | — | `RESCUE_OFFER` — autonomous win-back discount (simulated) |

**Risk signals** (`sentinel/risk.py`): amount spike vs customer average,
velocity (txns/10 min), new device, IP/billing geo mismatch, new payment
method, disposable email, CVV retries, coupon stacking, night-hour purchase,
first-order high value. Weights sum to a 0–100 score; every point carries a
human-readable reason consumed by the agent's narration.

## Model information (Stage II target)

The production agent runs an **INT8-quantized ~24B-class open LLM** on the
ASUS UGen **Intel Arc Pro B70 (32 GB GDDR6, 256 XMX engines, 367 INT8 TOPS,
608 GB/s)**:

| Candidate | License | INT8 footprint | Why |
|---|---|---|---|
| Mistral Small 4 (24B dense) | Apache 2.0 | ~24–26 GB (Q8) / ~14 GB (Q4_K_M) | primary pick — strong tool use + instruction following |
| Qwen3.5-27B (dense) | Apache 2.0 | ~27 GB (Q8) / ~17 GB (Q4_K_M) | strong multilingual + reasoning |
| Gemma 4 31B (dense) | Apache 2.0 | ~31 GB (Q8, tight) / ~18 GB (Q4_K_M) | fallback at Q4 |

Sizing math: 24B params × 1 byte (INT8) ≈ 24 GB weights + ~2–4 GB KV cache +
runtime overhead → fits the B70's 32 GB with headroom; Q4_K_M (~14–15 GB)
leaves room for 128K-token context and concurrent checkout streams. Serving
via an OpenAI-compatible runtime (llama.cpp GGUF / vLLM with Intel XPU
support) — which is exactly the protocol `LLMClient` already speaks, so the
Stage II swap is configuration, not a rewrite.

## Code documentation

| Module | Purpose |
|---|---|
| `app.py` | Flask app factory `create_app()`, `CheckoutSimulator` (seeded synthetic traffic), agent-loop wiring, REST API |
| `sentinel/risk.py` | `score_transaction(txn, history)` → `RiskResult(score, tier, signals)`; `TIER_BOUNDS`, signal weights |
| `sentinel/policy.py` | `decide(txn, tier, score, signals)` → `Intervention(action, priority, detail, rescue_code)` |
| `sentinel/agent.py` | `LLMClient` (OpenAI-compatible, honest template fallback), `template_narration()` |
| `sentinel/store.py` | `Store` — SQLite: `transactions`, `interventions`; `customer_history()`, `recent()`, `stats()` |
| `templates/dashboard.html` | Live dashboard: stats, agent narration panel, decision card, stream + intervention tables |
| `tests/` | 26 pytest tests: scorer (9), policy (7), agent (4), app/API (6) |

### API

- `GET /` — dashboard · `GET /api/health` — service status
- `POST /api/simulate` `{"force_event": "payment_attempt"|"abandoned"}` — run one event through the agent loop
- `GET /api/feed` — recent transactions + interventions · `GET /api/stats` — aggregate counters

## Originality

Written fresh for the ASUS UGen AI League, October 2026. Not previously
published, entered, or awarded (contest rules §9(1)). Architecture patterns
are informed by the author's prior portfolio work; all code, copy, and the
concept itself are new.
