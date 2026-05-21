"""DexScreener gateway — free, keyless, multi-chain DEX data.

Exposes two lookup modes:
  * ``by_address`` — deterministic path for known contract / mint.
  * ``by_query``   — free-text search across all chains.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .models import TokenTarget


_BASE = "https://api.dexscreener.com"


class DexGateway:
    def __init__(
        self,
        *,
        timeout: float = 30.0,
        http: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._own = http is None
        self._http = http or httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        if self._own:
            await self._http.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _fetch(self, path: str) -> dict:
        r = await self._http.get(f"{_BASE}{path}")
        r.raise_for_status()
        return r.json()

    async def by_query(self, q: str, *, strategy: str = "search") -> list[TokenTarget]:
        data = await self._fetch(f"/latest/dex/search?q={q}")
        return [_convert(p, strategy=strategy) for p in (data.get("pairs") or []) if p]

    async def by_address(self, addr: str, *, strategy: str = "address") -> list[TokenTarget]:
        data = await self._fetch(f"/latest/dex/tokens/{addr}")
        return [_convert(p, strategy=strategy) for p in (data.get("pairs") or []) if p]


def _convert(pair: dict, *, strategy: str) -> TokenTarget:
    base = pair.get("baseToken") or {}
    liq = (pair.get("liquidity") or {}).get("usd")
    vol = (pair.get("volume") or {}).get("h24")
    fdv = pair.get("fdv")
    price = pair.get("priceUsd")
    born = pair.get("pairCreatedAt")
    born_dt = (
        datetime.fromtimestamp(born / 1000, tz=timezone.utc)
        if isinstance(born, (int, float))
        else None
    )
    return TokenTarget(
        network=str(pair.get("chainId") or "unknown"),
        contract=str(base.get("address") or ""),
        ticker=str(base.get("symbol") or "?"),
        full_name=str(base.get("name") or "?"),
        dex_url=pair.get("url"),
        pool_liquidity=float(liq) if liq is not None else None,
        day_volume=float(vol) if vol is not None else None,
        spot_price=float(price) if price is not None else None,
        fully_diluted_val=float(fdv) if fdv is not None else None,
        pool_born=born_dt,
        hunt_strategy=strategy,
    )
