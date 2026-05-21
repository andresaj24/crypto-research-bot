"""Telegram alerter — sends briefs and summaries.  No-op when unconfigured."""

from __future__ import annotations

from typing import Optional

import httpx


class Alerter:
    def __init__(
        self,
        token: Optional[str],
        chat_id: Optional[str],
        *,
        timeout: float = 30.0,
    ) -> None:
        self.token = token
        self.chat_id = chat_id
        self._http = httpx.AsyncClient(timeout=timeout)

    @property
    def active(self) -> bool:
        return bool(self.token and self.chat_id)

    async def close(self) -> None:
        await self._http.aclose()

    async def push(self, text: str) -> bool:
        """Push a message.  Returns True on success."""
        if not self.active:
            return False
        body = text if len(text) <= 4096 else text[:4093] + "..."
        r = await self._http.post(
            f"https://api.telegram.org/bot{self.token}/sendMessage",
            json={
                "chat_id": self.chat_id,
                "text": body,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
        )
        return r.status_code == 200
