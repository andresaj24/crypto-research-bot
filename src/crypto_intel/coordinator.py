"""Coordinator — hub-and-spoke pipeline orchestrator.

Dispatches work to the four specialist agents in order:

    HunterAgent → VerifyAgent → IntelAgent → BriefAgent

Records every completed mission into the Ledger.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from .agents import BriefAgent, HunterAgent, IntelAgent, VerifyAgent
from .config import Env
from .ledger import Ledger
from .llm_client import Gateway
from .models import IntelBrief


@dataclass
class Coordinator:
    hunter: HunterAgent
    verifier: VerifyAgent
    intel: IntelAgent
    brief: BriefAgent
    _gw: Gateway
    _ledger: Optional[Ledger] = None

    @classmethod
    def build(cls, env: Env, *, ledger: Optional[Ledger] = None) -> "Coordinator":
        gw = Gateway(
            base_url=env.llm_base_url,
            api_key=env.llm_api_key,
            model=env.llm_model,
            ledger=ledger,
        )
        return cls(
            hunter=HunterAgent(),
            verifier=VerifyAgent(
                etherscan_key=env.etherscan_key,
                solana_rpc=env.solana_rpc,
            ),
            intel=IntelAgent(gw=gw),
            brief=BriefAgent(gw=gw),
            _gw=gw,
            _ledger=ledger,
        )

    async def close(self) -> None:
        await self.hunter.close()
        await self.verifier.close()
        await self._gw.close()

    async def execute(
        self,
        seed: str,
        *,
        top_k: int = 1,
        strategy: str = "auto",
    ) -> list[IntelBrief]:
        """Run the full pipeline for *seed*, returning up to *top_k* briefs."""
        targets = await self.hunter.hunt(seed, top_k=top_k, strategy=strategy)
        briefs: list[IntelBrief] = []
        for tgt in targets:
            t0 = time.monotonic()
            tok_before = self._ledger.total_tokens() if self._ledger else 0

            ci = await self.verifier.check(tgt)
            assessment = await self.intel.assess(tgt, ci)
            ib = await self.brief.compose(tgt, ci, assessment)
            briefs.append(ib)

            if self._ledger is not None:
                tok_after = self._ledger.total_tokens()
                self._ledger.log_mission(
                    ref=seed,
                    network=tgt.network,
                    contract=tgt.contract,
                    ticker=tgt.ticker,
                    threat=assessment.threat_score,
                    signal=assessment.signal.value,
                    tokens_used=tok_after - tok_before,
                    ms=int((time.monotonic() - t0) * 1000),
                )
        return briefs

    async def __aenter__(self) -> "Coordinator":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
