"""Typed contracts exchanged between agents.

Naming convention:
    TokenTarget      — output of HunterAgent
    ChainIntel       — output of VerifyAgent
    ThreatAssessment — output of IntelAgent
    IntelBrief       — final deliverable from BriefAgent
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Signal classification ────────────────────────────────────────────────

class Signal(str, Enum):
    """Traffic-light classification used across the system."""

    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"


# ── HunterAgent output ───────────────────────────────────────────────────

class TokenTarget(BaseModel):
    """A token worth investigating, discovered by the HunterAgent."""

    network: str = Field(description="Chain slug, e.g. 'ethereum', 'solana', 'base'.")
    contract: str = Field(description="Contract / mint address.")
    ticker: str
    full_name: str
    dex_url: Optional[str] = None
    pool_liquidity: Optional[float] = Field(default=None, description="USD liquidity in the pool.")
    day_volume: Optional[float] = Field(default=None, description="24 h trading volume (USD).")
    spot_price: Optional[float] = None
    fully_diluted_val: Optional[float] = None
    pool_born: Optional[datetime] = Field(default=None, description="When the pair was created.")
    hunt_strategy: str = Field(
        description="Strategy that surfaced this target, e.g. 'volume_spike', 'new_launch'."
    )


# ── VerifyAgent output ───────────────────────────────────────────────────

class ChainIntel(BaseModel):
    """Onchain facts gathered by the VerifyAgent."""

    contract: str
    network: str
    source_public: Optional[bool] = Field(
        default=None, description="True if contract source is verified on explorer."
    )
    holders: Optional[int] = None
    whale_share_pct: Optional[float] = Field(
        default=None, description="Largest non-LP holder share (0-100)."
    )
    honeypot_flag: Optional[bool] = None
    findings: list[str] = Field(default_factory=list)


# ── IntelAgent output ────────────────────────────────────────────────────

class ThreatAssessment(BaseModel):
    """Structured threat & opportunity analysis from the IntelAgent."""

    threat_score: int = Field(ge=0, le=100, description="0 = benign, 100 = extreme threat.")
    opportunity_score: int = Field(ge=0, le=100, description="0 = no opportunity, 100 = prime.")
    signal: Signal
    confidence_pct: int = Field(ge=0, le=100, description="How confident the model is.")
    indicators: list[str] = Field(default_factory=list, description="Key indicators observed.")
    reasoning: str = Field(description="Chain-of-thought explanation.")


# ── BriefAgent output ────────────────────────────────────────────────────

class IntelBrief(BaseModel):
    """Final intelligence briefing — the deliverable."""

    target: TokenTarget
    chain_intel: ChainIntel
    assessment: ThreatAssessment
    briefing_md: str = Field(description="Markdown-formatted BLUF intelligence brief.")
    produced_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
