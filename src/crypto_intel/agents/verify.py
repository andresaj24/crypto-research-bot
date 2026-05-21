"""VerifyAgent — deterministic onchain verification.

For EVM chains: queries Etherscan v2 multichain API for source-code
verification status.

For Solana: queries the configured RPC for account info (SPL token
programme ownership check).

No LLM calls — purely factual checks.
"""

from __future__ import annotations

from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import ChainIntel, TokenTarget


_ETHERSCAN_V2 = "https://api.etherscan.io/v2/api"

_NETWORK_TO_CHAIN: dict[str, int] = {
    "ethereum": 1,
    "bsc": 56,
    "polygon": 137,
    "arbitrum": 42161,
    "optimism": 10,
    "base": 8453,
    "avalanche": 43114,
    "fantom": 250,
}


class VerifyAgent:
    def __init__(
        self,
        etherscan_key: Optional[str] = None,
        solana_rpc: Optional[str] = None,
        *,
        timeout: float = 30.0,
        http: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.etherscan_key = etherscan_key
        self.solana_rpc = solana_rpc
        self._own = http is None
        self._http = http or httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        if self._own:
            await self._http.aclose()

    async def check(self, target: TokenTarget) -> ChainIntel:
        ci = ChainIntel(contract=target.contract, network=target.network)

        if target.network.lower() == "solana":
            await self._check_solana(ci)
            return ci

        chain_id = _NETWORK_TO_CHAIN.get(target.network.lower())
        if not self.etherscan_key or not chain_id:
            reason = "no API key" if not self.etherscan_key else f"unsupported network {target.network!r}"
            ci.findings.append(f"explorer skipped: {reason}")
            return ci

        try:
            verified = await self._source_verified(chain_id, target.contract)
            ci.source_public = verified
            if verified is False:
                ci.findings.append("contract source NOT verified on block explorer")
        except httpx.HTTPError as exc:
            ci.findings.append(f"explorer request failed: {exc.__class__.__name__}")

        return ci

    # ── Solana path ──────────────────────────────────────────────

    async def _check_solana(self, ci: ChainIntel) -> None:
        if not self.solana_rpc:
            ci.findings.append("solana RPC not configured — skipping")
            return
        try:
            r = await self._http.post(
                self.solana_rpc,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getAccountInfo",
                    "params": [ci.contract, {"encoding": "jsonParsed"}],
                },
            )
            r.raise_for_status()
            val = (r.json().get("result") or {}).get("value")
            if val:
                owner = val.get("owner", "")
                ci.findings.append("account exists on Solana")
                if owner == "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA":
                    ci.findings.append("owned by SPL Token programme")
                elif owner == "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb":
                    ci.findings.append("owned by Token-2022 programme")
            else:
                ci.findings.append("account NOT found on Solana")
        except httpx.HTTPError as exc:
            ci.findings.append(f"solana RPC error: {exc.__class__.__name__}")

    # ── EVM path ─────────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _source_verified(self, chain_id: int, address: str) -> Optional[bool]:
        params = {
            "chainid": chain_id,
            "module": "contract",
            "action": "getsourcecode",
            "address": address,
            "apikey": self.etherscan_key,
        }
        r = await self._http.get(_ETHERSCAN_V2, params=params)
        r.raise_for_status()
        result = r.json().get("result")
        if not isinstance(result, list) or not result:
            return None
        return bool((result[0].get("SourceCode") or "").strip())
