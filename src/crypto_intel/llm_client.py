"""Unified LLM gateway — talks to any OpenAI-compatible endpoint.

Features beyond a raw HTTP call:
  * Automatic retries with exponential backoff.
  * Token-usage recording into the ``Ledger``.
  * ``ask_json`` with best-effort JSON extraction when the provider
    ignores ``response_format``.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .ledger import Ledger


class Gateway:
    """Async wrapper around an OpenAI-compatible chat/completions endpoint."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        timeout: float = 120.0,
        http: Optional[httpx.AsyncClient] = None,
        ledger: Optional[Ledger] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.ledger = ledger
        self._own = http is None
        self._http = http or httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        if self._own:
            await self._http.aclose()

    async def __aenter__(self) -> "Gateway":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # ── core call ────────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        reraise=True,
    )
    async def ask(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        fmt: Optional[dict[str, Any]] = None,
        tag: str = "unknown",
        ref: Optional[str] = None,
    ) -> str:
        """Send a chat completion and return the assistant's text."""
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if fmt is not None:
            body["response_format"] = fmt

        t0 = time.monotonic()
        resp = await self._http.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
        elapsed = int((time.monotonic() - t0) * 1000)

        if self.ledger is not None:
            u = data.get("usage") or {}
            self.ledger.log_call(
                tag=tag,
                model=self.model,
                prompt_tok=int(u.get("prompt_tokens") or 0),
                gen_tok=int(u.get("completion_tokens") or 0),
                ref=ref,
                ms=elapsed,
            )

        return data["choices"][0]["message"].get("content") or ""

    # ── JSON variant ─────────────────────────────────────────────

    async def ask_json(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        tag: str = "unknown",
        ref: Optional[str] = None,
    ) -> dict[str, Any]:
        """Ask for JSON.  Falls back to regex extraction when the
        provider silently ignores ``response_format``."""
        try:
            raw = await self.ask(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                fmt={"type": "json_object"},
                tag=tag,
                ref=ref,
            )
        except httpx.HTTPStatusError:
            raw = await self.ask(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                tag=tag,
                ref=ref,
            )

        return _extract_json(raw)


def _extract_json(text: str) -> dict[str, Any]:
    """Best-effort JSON object extraction."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return {"_raw": text}
