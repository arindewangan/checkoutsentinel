# CheckoutSentinel — Concept

**ASUS UGen AI League · Battlefield Thunderstorm · Global Online Track · Stage I**
**Theme: Workplace AI** (merchant operations / revenue protection)

## The problem

Every e-commerce checkout is a split-second bet. Merchants lose on **both**
sides of it:

1. **Fraud costs real money.** Card-not-present fraud, account takeovers, and
   friendly fraud drain an estimated tens of billions annually; the average
   merchant pays back ~$3–4 for every $1 of fraud in chargebacks, fees, and
   lost goods. Rule-based filters are blunt: they either miss novel patterns
   or nuke legitimate orders.
2. **False declines cost more than fraud.** Over-zealous fraud filters decline
   legitimate customers — industry studies put false-decline losses several
   times higher than actual fraud losses. Every hard decline is a customer who
   may never come back.
3. **Cart abandonment is a silent bleed.** ~70% of carts are abandoned; a large
   share of abandoners are price-sensitive, not uninterested. Static "10% off"
   popups train customers to abandon on purpose.

The missing piece is **judgment at checkout speed**: a per-transaction analyst
that can read the signals, narrate the risk, and take the *right-sized*
action — approve, verify, rescue, or hold — in milliseconds, thousands of
times per second, without sending sensitive payment data to a third-party
cloud.

## The solution: CheckoutSentinel

CheckoutSentinel is a **real-time agentic checkout guard**. An agentic loop
watches every checkout event and, per transaction:

1. **Scores risk** — a signal engine evaluates amount anomalies, velocity,
   device/geo consistency, payment friction (CVV retries), coupon behavior,
   and email reputation into an explainable 0–100 score with 4 tiers.
2. **Decides autonomously** — an intervention policy takes the right-sized
   action:
   - LOW → auto-approve, zero friction
   - MEDIUM → approve + async analyst flag (conversion protected)
   - HIGH → step-up authentication; rescue incentive for returning shoppers
   - CRITICAL → hold capture, P1 manual review
   - Abandoned cart (low risk) → autonomous win-back discount (revenue recovery)
3. **Narrates** — a ~24B-class LLM agent writes a per-transaction analyst note
   (what it saw, why the action is right, the conversion-vs-risk tradeoff),
   giving merchants an audit trail that reads like a human analyst wrote it.

The demo in this repo (`app.py`) implements the full loop with a simulated
checkout stream, heuristic scorer, policy engine, and template narration
(clearly labeled). Stage II replaces the templates with the real LLM agent —
the integration seam (`LLMClient`, OpenAI-compatible protocol) is already in
place.

## Why it fits Battlefield Thunderstorm

Thunderstorm is the **high-performance development** battlefield: workloads
that need serious local compute, low latency, and high throughput. CheckoutSentinel
is a textbook fit:

- **Per-transaction agent inference is the workload.** Each checkout triggers
  an agent turn: signal summary → policy check → 2–3 sentence narration. At
  production scale that's hundreds of concurrent agent inferences — exactly
  the high-throughput, low-latency inference profile the B70 is built for.
- **The latency story is the product story.** Checkout decisions must land in
  **< 300 ms** end-to-end or they cost conversions. A 24B-class model in INT8
  on the B70's 256 XMX engines (367 INT8 TOPS, 608 GB/s) delivers the
  tokens-per-second headroom to run the agent *inline* in the payment path,
  not as an offline batch job. Cloud APIs can't guarantee that latency or
  data residency; a local B70 can.
- **Data never leaves the merchant.** Payment data is the most regulated data
  there is (PCI DSS, GDPR, India's DPDP Act). Local inference on merchant-owned
  hardware turns compliance from a liability into a selling point.
- **Unit economics.** Cloud LLM APIs charge per token; a busy store doing
  millions of checkouts/month pays per-transaction forever. A $949 B70-class
  card amortizes to near-zero marginal cost per decision — the commercial
  argument writes itself.

## Hardware / software architecture (Stage II target)

```
                    ┌─────────────────────────────────────────┐
                    │  Store checkout service (webhook/stream) │
                    └───────────────┬─────────────────────────┘
                                    │ checkout events (JSON)
                                    ▼
┌──────────────────────────────────────────────────────────────────┐
│  ASUS UGen node — Intel Arc Pro B70 (32 GB, 367 INT8 TOPS)        │
│                                                                  │
│  ┌──────────┐   ┌──────────────┐   ┌─────────────────────────┐   │
│  │ signal   │──▶│ policy       │──▶│ agent (24B INT8 LLM,     │   │
│  │ engine   │   │ engine       │   │ OpenAI-compat server)   │   │
│  │ (CPU)    │   │ (CPU)        │   │ • risk narration        │   │
│  └──────────┘   └──────────────┘   │ • intervention drafts   │   │
│                                    │ • analyst summaries     │   │
│  ┌──────────┐                      └─────────────────────────┘   │
│  │ SQLite / │◀── decisions, narrations, audit log                │
│  │ Postgres │                                                   │
│  └──────────┘                                                   │
└──────────────────────────────────────────────────────────────────┘
        │ actions back to store: approve / 3DS challenge /
        │ rescue code / review-queue ticket
```

- **Compute:** single B70 holds the 24B INT8 agent (~24–26 GB) + KV cache with
  headroom; CPU handles the deterministic signal/policy layers (microseconds).
- **Serving:** OpenAI-compatible inference server (llama.cpp GGUF / vLLM with
  Intel XPU backend via oneAPI/IPEX) — the prototype's `LLMClient` already
  speaks this protocol, so Stage II is a config change, not a rewrite.
- **Data plane:** SQLite in the demo → Postgres/Redis Streams in production;
  every decision is immutable and auditable (regulator-friendly).
- **Integration:** one webhook + a JS snippet; Shopify/WooCommerce plugins in
  the commercial roadmap.

## Model information

| Candidate (Stage II) | License | INT8 size | Verdict |
|---|---|---|---|
| **Mistral Small 4 — 24B dense** | Apache 2.0 | ~24–26 GB (Q8) / ~14 GB (Q4_K_M) | **Primary.** Strong tool use, instruction following, 128K context |
| Qwen3.5-27B dense | Apache 2.0 | ~27 GB (Q8) / ~17 GB (Q4_K_M) | Alt — strong reasoning, multilingual |
| Gemma 4 31B dense | Apache 2.0 | ~31 GB (Q8, tight) / ~18 GB (Q4_K_M) | Fallback at Q4_K_M |

Sizing: 24B params × 1 byte (INT8) ≈ 24 GB + 2–4 GB KV cache + overhead —
fits the B70's 32 GB ECC VRAM with margin; Q4_K_M leaves room for long
context and concurrent streams. All candidates are permissively licensed
(Apache 2.0) for commercial use. A small distilled classifier head
(< 1B params) can pre-filter the obvious cases on CPU/XMX so the 24B agent
only narrates the interesting ones — throughput engineering for Stage II.

## Commercial potential

- **Market:** e-commerce fraud-prevention and conversion-optimization tooling
  is a multi-billion-dollar market (fraud platforms, 3-D Secure orchestration,
  cart-recovery email). CheckoutSentinel collapses three SKUs — fraud scoring,
  step-up orchestration, abandonment recovery — into one agent.
- **Pricing:** SaaS per-order-decision pricing (e.g., $0.01–0.03/decision) or
  a performance model (share of recovered revenue). At 1M checkouts/month, a
  merchant pays ~$10–30K/month vs. fraud losses an order of magnitude higher.
- **Moat:** the agentic narration + autonomous intervention loop is hard to
  replicate with rules; the local-inference deployment story (B70-class
  hardware, data residency) wins regulated verticals (fintech, D2C in
  EU/India) that US-cloud-only vendors can't serve cleanly.
- **Go-to-market:** Shopify/WooCommerce app stores → mid-market D2C brands →
  enterprise via the compliance story. Stage II demo targets a live Shopify
  sandbox store.

## Originality (§9(1))

CheckoutSentinel was conceived and built fresh for the ASUS UGen AI League
(October 2026). It has not been previously published, entered in any
competition, or awarded. Architecture patterns are informed by the author's
prior portfolio work; all code, copy, branding, and the concept itself are
new and original to this entry.
