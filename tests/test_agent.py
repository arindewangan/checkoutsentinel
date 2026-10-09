"""Tests for the agentic narration layer (sentinel/agent.py)."""
from sentinel.agent import LLMClient, template_narration

TXN = {"txn_ref": "txn_demo1", "amount": 299.0, "currency": "USD",
       "event": "payment_attempt"}


def test_template_narration_labels_simulated():
    text = template_narration(TXN, "HIGH", 72, "geo_mismatch (+15)", "STEP_UP_AUTH", "d")
    assert "SIMULATED" in text
    assert "72/100" in text and "HIGH" in text and "STEP_UP_AUTH" not in text  # action read, not raw code
    assert "step-up authentication" in text.lower()


def test_template_narration_is_deterministic():
    a = template_narration(TXN, "LOW", 5, "no risk indicators", "ALLOW", "d")
    b = template_narration(TXN, "LOW", 5, "no risk indicators", "ALLOW", "d")
    assert a == b


def test_unconfigured_client_falls_back_to_template():
    client = LLMClient(base_url="")
    text, mode = client.narrate(TXN, "MEDIUM", 40, "velocity", "SOFT_REVIEW", "d")
    assert mode == "template" and "SIMULATED" in text
    assert not client.configured


def test_unreachable_endpoint_falls_back_without_raising():
    client = LLMClient(base_url="http://127.0.0.1:1", timeout=1.0)
    assert client.configured  # URL set, but nothing listens there
    text, mode = client.narrate(TXN, "LOW", 8, "no risk indicators", "ALLOW", "d")
    assert mode == "template" and isinstance(text, str)
