"""Tests for the IntelAgent — LLM mocked."""

from typing import Any

import pytest

from crypto_intel.agents.intel import IntelAgent
from crypto_intel.models import ChainIntel, Signal, ThreatAssessment, TokenTarget


class _FakeGW:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls = 0

    async def ask_json(self, **_: Any) -> dict[str, Any]:
        self.calls += 1
        return self.payload


def _target() -> TokenTarget:
    return TokenTarget(
        network="ethereum",
        contract="0x" + "0" * 40,
        ticker="TEST",
        full_name="Test Token",
        hunt_strategy="test",
    )


@pytest.mark.asyncio
async def test_well_formed_response() -> None:
    gw = _FakeGW({
        "threat_score": 25,
        "opportunity_score": 60,
        "signal": "GREEN",
        "confidence_pct": 80,
        "indicators": ["verified_source", "good_liquidity"],
        "reasoning": "Looks safe.",
    })
    agent = IntelAgent(gw=gw)  # type: ignore[arg-type]
    ci = ChainIntel(contract="0x" + "0" * 40, network="ethereum")
    result = await agent.assess(_target(), ci)

    assert isinstance(result, ThreatAssessment)
    assert result.threat_score == 25
    assert result.opportunity_score == 60
    assert result.signal == Signal.GREEN
    assert result.confidence_pct == 80
    assert gw.calls == 1


@pytest.mark.asyncio
async def test_malformed_response_falls_back() -> None:
    gw = _FakeGW({"threat_score": "garbage", "reasoning": "dunno"})
    agent = IntelAgent(gw=gw)  # type: ignore[arg-type]
    ci = ChainIntel(contract="0x" + "0" * 40, network="ethereum")
    result = await agent.assess(_target(), ci)

    assert result.threat_score == 75
    assert result.signal == Signal.RED
    assert result.confidence_pct == 30


@pytest.mark.asyncio
async def test_amber_signal() -> None:
    gw = _FakeGW({
        "threat_score": 50,
        "opportunity_score": 40,
        "signal": "AMBER",
        "confidence_pct": 55,
        "indicators": ["moderate_risk"],
        "reasoning": "Mixed signals.",
    })
    agent = IntelAgent(gw=gw)  # type: ignore[arg-type]
    ci = ChainIntel(contract="0x" + "0" * 40, network="ethereum")
    result = await agent.assess(_target(), ci)
    assert result.signal == Signal.AMBER
