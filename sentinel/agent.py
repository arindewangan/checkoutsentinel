"""Agentic narration layer.

In production (Stage II) the agent is an INT8-quantized ~24B-class open LLM
served from an OpenAI-compatible endpoint running on the ASUS UGen
Intel Arc Pro B70. This module speaks that protocol through ``LLMClient``.

DEMO MODE (this prototype): when no ``LLM_BASE_URL`` is configured — or the
endpoint is unreachable — narration falls back to deterministic templates and
is ALWAYS labeled ``mode="template"``. The dashboard surfaces this label, so
nothing presented as AI output is faked.
"""
from __future__ import annotations

import os
import random

try:
    import requests
except ImportError:  # pragma: no cover - requests is in requirements.txt
    requests = None


class LLMClient:
    """Thin OpenAI-compatible chat client with honest fallback."""

    def __init__(self, base_url: str | None = None, model: str | None = None,
                 timeout: float = 8.0):
        self.base_url = (base_url or os.getenv("LLM_BASE_URL") or "").rstrip("/")
        self.model = model or os.getenv("LLM_MODEL", "checkoutsentinel-24b-int8")
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.base_url) and requests is not None

    def narrate(self, txn: dict, tier: str, score: int,
                reasons: str, action: str, detail: str) -> tuple[str, str]:
        """Return (narration_text, mode) where mode is 'llm' or 'template'."""
        if self.configured:
            text = self._call_llm(txn, tier, score, reasons, action, detail)
            if text:
                return text, "llm"
        return template_narration(txn, tier, score, reasons, action, detail), "template"

    def _call_llm(self, txn, tier, score, reasons, action, detail) -> str | None:
        system = (
            "You are CheckoutSentinel, a fraud-and-conversion analyst for e-commerce "
            "checkout. Given a transaction's risk tier, score, signals and the "
            "intervention taken, write a 2-3 sentence analyst note: what you saw, "
            "why the action is right, and the conversion-vs-risk tradeoff. "
            "Be concrete, cite the signals, no hedging filler."
        )
        user = (
            f"amount=${float(txn.get('amount', 0)):.2f} {txn.get('currency', 'USD')} "
            f"event={txn.get('event')} tier={tier} score={score}/100 "
            f"signals=[{reasons}] action={action} detail={detail}"
        )
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                json={"model": self.model,
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": user}],
                      "temperature": 0.3, "max_tokens": 220},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            return None  # honest fallback: caller labels mode="template"


_TEMPLATE_OPENERS = [
    "Sentinel here. I reviewed this checkout",
    "Checkout analysis complete",
    "Risk review finished",
]

_TEMPLATE_TAKES = {
    "LOW": "the profile is clean and consistent with the customer's history",
    "MEDIUM": "a couple of soft signals are worth an analyst's eye, but nothing that justifies blocking a paying customer",
    "HIGH": "several strong fraud indicators cluster on this attempt, so friction is warranted before money moves",
    "CRITICAL": "the signal cluster matches known fraud patterns closely enough that capture must be held",
}

_ACTION_READS = {
    "ALLOW": "auto-approved with zero added friction",
    "SOFT_REVIEW": "auto-approved to protect conversion, with an async analyst flag attached",
    "STEP_UP_AUTH": "gated behind step-up authentication — the customer proves identity, the merchant keeps the sale",
    "RESCUE_OFFER": "answered with a win-back incentive rather than a wall — revenue recovery over rejection",
    "MANUAL_REVIEW": "parked in the analyst queue with full signal context attached",
    "HOLD_CAPTURE": "capture held and the case escalated — this one needs human eyes before settlement",
}


def template_narration(txn: dict, tier: str, score: int,
                       reasons: str, action: str, detail: str) -> str:
    """Deterministic, clearly-labeled stand-in for the LLM agent's narration."""
    rng = random.Random(hash((txn.get("txn_ref", ""), tier, score)) & 0xFFFFFFFF)
    opener = rng.choice(_TEMPLATE_OPENERS)
    take = _TEMPLATE_TAKES.get(tier, "the picture is mixed")
    read = _ACTION_READS.get(action, "handled per policy")
    return (
        f"{opener}: {take} (risk {score}/100, {tier}). "
        f"Key signals — {reasons}. "
        f"Intervention: {read}. "
        f"[SIMULATED narration: template-based demo output, not from a live LLM]"
    )
