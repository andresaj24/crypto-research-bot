"""HunterAgent — multi-strategy token discovery.

Strategies:
  * ``address``      — direct contract / mint lookup via DexScreener.
  * ``search``       — free-text query (symbol, name, keyword).
  * ``volume_spike`` — search then filter for tokens whose 24 h volume
                       is >=2x their pool liquidity (anomaly heuristic).
  * ``fresh_pool``   — search then keep only pairs younger than 48 h.

The Hunter is entirely deterministic — no LLM calls.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

from ..dex import DexGateway
from ..models import TokenTarget


_EVM_LEN = 42
_SOL_MIN = 32
_FRESH_HOURS = 48
_SPIKE_RATIO = 2.0


class HunterAgent:
    def __init__(self, dex: Optional[DexGateway] = None) -> None:
        self._own = dex is None
        self.dex = dex or DexGateway()

    async def close(self) -> None:
        if self._own:
            await self.dex.close()

    async def hunt(
        self,
        seed: str,
        *,
        top_k: int = 3,
        strategy: str = "auto",
    ) -> list[TokenTarget]:
        """Return up to *top_k* targets for *seed* using *strategy*."""
        seed = seed.strip()
        if not seed:
            return []

        if strategy == "auto":
            strategy = _pick_strategy(seed)

        if strategy == "address":
            raw = await self.dex.by_address(seed, strategy="address")
        else:
            raw = await self.dex.by_query(seed, strategy=strategy)

        filtered = _apply_filter(raw, strategy)
        ranked = sorted(filtered, key=_rank, reverse=True)
        return ranked[:top_k]


def _pick_strategy(seed: str) -> str:
    if seed.lower().startswith("0x") and len(seed) == _EVM_LEN:
        return "address"
    if len(seed) >= _SOL_MIN and seed.isalnum():
        return "address"
    return "search"


def _apply_filter(targets: list[TokenTarget], strategy: str) -> list[TokenTarget]:
    if strategy == "volume_spike":
        return [
            t for t in targets
            if (t.day_volume or 0) >= _SPIKE_RATIO * (t.pool_liquidity or 1)
        ]
    if strategy == "fresh_pool":
        cutoff = datetime.now(timezone.utc) - timedelta(hours=_FRESH_HOURS)
        return [t for t in targets if t.pool_born is not None and t.pool_born >= cutoff]
    return targets


def _rank(t: TokenTarget) -> float:
    """Composite score: liquidity dominant, volume secondary, recency bonus."""
    liq = t.pool_liquidity or 0.0
    vol = t.day_volume or 0.0
    age_bonus = 0.0
    if t.pool_born is not None:
        age_h = (datetime.now(timezone.utc) - t.pool_born).total_seconds() / 3600
        if age_h < 24:
            age_bonus = 500.0
        elif age_h < 168:
            age_bonus = 100.0
    return liq + 0.1 * vol + age_bonus
