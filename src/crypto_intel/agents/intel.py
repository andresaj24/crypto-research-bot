"""IntelAgent — LLM-powered threat & opportunity analysis.

Unlike a simple risk scorer, the IntelAgent produces a **dual-axis**
assessment: threat (how dangerous) *and* opportunity (how promising).
It also reports a confidence percentage so downstream consumers can
weight the result appropriately.

The prompt asks the model to walk through seven intelligence dimensions
before emitting the final JSON — this forces chain-of-thought reasoning.
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from ..llm_client import Gateway
from ..models import ChainIntel, Signal, ThreatAssessment, TokenTarget


_SYSTEM = (
    "You are a crypto intelligence analyst specialising in DeFi threat "
    "assessment.  You produce structured JSON evaluations covering both "
    "threats (rug-pull, honeypot, low liquidity, concentration) AND "
    "opportunities (strong liquidity, growing volume, verified contract, "
    "healthy age).  Be precise and conservative.  When uncertain, raise "
    "the threat score and lower confidence."
)

_SCHEMA = """{
  "threat_score": <int 0-100, 0=benign 100=extreme>,
  "opportunity_score": <int 0-100, 0=none 100=prime>,
  "signal": "GREEN" | "AMBER" | "RED",
  "confidence_pct": <int 0-100>,
  "indicators": [<short strings, e.g. "verified_source", "thin_liquidity">],
  "reasoning": "<3-5 sentences walking through the dimensions>"
}"""

_DIMENSIONS = [
    "pool_liquidity_usd",
    "volume_to_liquidity_ratio",
    "fdv_to_liquidity_ratio",
    "pool_age_hours",
    "source_verification",
    "holder_concentration",
    "onchain_findings",
]


class IntelAgent:
    TAG = "intel"

    def __init__(self, gw: Gateway) -> None:
        self.gw = gw

    async def assess(
        self, target: TokenTarget, chain_intel: ChainIntel
    ) -> ThreatAssessment:
        prompt = _build_prompt(target, chain_intel)
        ref = f"{target.network}:{target.contract}"
        data = await self.gw.ask_json(
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.15,
            max_tokens=1800,
            tag=self.TAG,
            ref=ref,
        )
        try:
            return ThreatAssessment(**data)
        except (ValidationError, ValueError):
            return _fallback(data)


def _build_prompt(t: TokenTarget, ci: ChainIntel) -> str:
    payload = {
        "target": t.model_dump(mode="json"),
        "chain_intel": ci.model_dump(mode="json"),
        "dimensions": _DIMENSIONS,
    }
    return (
        "Analyse the following token.  Walk through every item in "
        "`dimensions` before producing your verdict.  Return ONLY a "
        "JSON object matching this schema:\n\n"
        f"{_SCHEMA}\n\n"
        f"Data:\n{json.dumps(payload, indent=2, default=str)}"
    )


def _fallback(data: dict) -> ThreatAssessment:
    """Best-effort coercion when the LLM returns an off-shape reply."""

    def _int(key: str, default: int) -> int:
        v = data.get(key, default)
        return int(v) if isinstance(v, (int, float)) else default

    signal_raw = str(data.get("signal", "RED")).upper()
    signal = Signal(signal_raw) if signal_raw in Signal.__members__ else Signal.RED

    return ThreatAssessment(
        threat_score=min(max(_int("threat_score", 75), 0), 100),
        opportunity_score=min(max(_int("opportunity_score", 10), 0), 100),
        signal=signal,
        confidence_pct=min(max(_int("confidence_pct", 30), 0), 100),
        indicators=[str(i) for i in (data.get("indicators") or [])],
        reasoning=str(data.get("reasoning", "Schema mismatch — defaulted to RED.")),
    )
