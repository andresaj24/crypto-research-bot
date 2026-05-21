"""Tests for the HunterAgent — deterministic, no network calls."""

from datetime import datetime, timezone, timedelta

import pytest

from crypto_intel.agents.hunter import HunterAgent, _pick_strategy, _rank
from crypto_intel.models import TokenTarget


class _StubDex:
    """In-memory DexGateway replacement."""

    def __init__(self, pairs: list[TokenTarget]) -> None:
        self._pairs = pairs
        self.last: tuple[str, str] | None = None

    async def by_query(self, q: str, *, strategy: str = "search") -> list[TokenTarget]:
        self.last = ("query", q)
        return list(self._pairs)

    async def by_address(self, addr: str, *, strategy: str = "address") -> list[TokenTarget]:
        self.last = ("address", addr)
        return list(self._pairs)

    async def close(self) -> None:
        pass


def _tgt(ticker: str, liq: float = 0, vol: float = 0, age_h: float | None = None) -> TokenTarget:
    born = (
        datetime.now(timezone.utc) - timedelta(hours=age_h) if age_h is not None else None
    )
    return TokenTarget(
        network="ethereum",
        contract="0x" + "a" * 40,
        ticker=ticker,
        full_name=ticker,
        pool_liquidity=liq,
        day_volume=vol,
        pool_born=born,
        hunt_strategy="test",
    )


@pytest.mark.asyncio
async def test_evm_address_routes_to_by_address() -> None:
    dex = _StubDex([_tgt("X", liq=100)])
    h = HunterAgent(dex=dex)  # type: ignore[arg-type]
    addr = "0x" + "1" * 40
    out = await h.hunt(addr, top_k=5)
    assert dex.last == ("address", addr)
    assert len(out) == 1


@pytest.mark.asyncio
async def test_solana_address_routes_to_by_address() -> None:
    dex = _StubDex([_tgt("BONK", liq=500)])
    h = HunterAgent(dex=dex)  # type: ignore[arg-type]
    sol_addr = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
    out = await h.hunt(sol_addr, top_k=5)
    assert dex.last == ("address", sol_addr)
    assert out[0].ticker == "BONK"


@pytest.mark.asyncio
async def test_symbol_routes_to_search() -> None:
    dex = _StubDex([_tgt("A", liq=10), _tgt("B", liq=1000)])
    h = HunterAgent(dex=dex)  # type: ignore[arg-type]
    out = await h.hunt("PEPE", top_k=2)
    assert dex.last == ("query", "PEPE")
    assert out[0].ticker == "B"  # higher liquidity ranked first


@pytest.mark.asyncio
async def test_empty_seed() -> None:
    h = HunterAgent(dex=_StubDex([]))  # type: ignore[arg-type]
    assert await h.hunt("   ") == []


@pytest.mark.asyncio
async def test_volume_spike_strategy_filters() -> None:
    dex = _StubDex([
        _tgt("NORMAL", liq=1000, vol=500),
        _tgt("SPIKE", liq=1000, vol=3000),
    ])
    h = HunterAgent(dex=dex)  # type: ignore[arg-type]
    out = await h.hunt("any", top_k=10, strategy="volume_spike")
    assert len(out) == 1
    assert out[0].ticker == "SPIKE"


@pytest.mark.asyncio
async def test_fresh_pool_strategy_filters() -> None:
    dex = _StubDex([
        _tgt("OLD", liq=1000, age_h=100),
        _tgt("NEW", liq=500, age_h=12),
    ])
    h = HunterAgent(dex=dex)  # type: ignore[arg-type]
    out = await h.hunt("any", top_k=10, strategy="fresh_pool")
    assert len(out) == 1
    assert out[0].ticker == "NEW"


def test_strategy_detection() -> None:
    assert _pick_strategy("0x" + "a" * 40) == "address"
    assert _pick_strategy("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v") == "address"
    assert _pick_strategy("PEPE") == "search"


def test_rank_gives_recency_bonus() -> None:
    fresh = _tgt("NEW", liq=100, age_h=6)
    old = _tgt("OLD", liq=100, age_h=300)
    assert _rank(fresh) > _rank(old)
