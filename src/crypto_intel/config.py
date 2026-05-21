"""Environment-based configuration loader."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


@dataclass(frozen=True)
class Env:
    """Immutable runtime configuration resolved from env vars / .env."""

    llm_base_url: str
    llm_api_key: str
    llm_model: str
    etherscan_key: Optional[str]
    solana_rpc: Optional[str]
    tg_token: Optional[str]
    tg_chat: Optional[str]

    @property
    def telegram_ready(self) -> bool:
        return bool(self.tg_token and self.tg_chat)


def load_env(dotenv: Optional[Path] = None) -> Env:
    """Read .env (if any) then overlay process env vars."""
    if dotenv is not None:
        load_dotenv(dotenv, override=False)
    else:
        load_dotenv(override=False)

    base = os.getenv("LLM_BASE_URL", "").strip()
    key = os.getenv("LLM_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL", "").strip()

    if not base or not key or not model:
        raise RuntimeError(
            "LLM not configured. Export LLM_BASE_URL, LLM_API_KEY, LLM_MODEL "
            "(see .env.example)."
        )

    return Env(
        llm_base_url=base.rstrip("/"),
        llm_api_key=key,
        llm_model=model,
        etherscan_key=os.getenv("ETHERSCAN_API_KEY") or None,
        solana_rpc=os.getenv("SOLANA_RPC_URL") or None,
        tg_token=os.getenv("TELEGRAM_BOT_TOKEN") or None,
        tg_chat=os.getenv("TELEGRAM_CHAT_ID") or None,
    )
