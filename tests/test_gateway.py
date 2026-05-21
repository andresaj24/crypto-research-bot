"""Tests for the LLM Gateway — mocked HTTP, no real calls."""

from pathlib import Path
from typing import Any

import httpx
import pytest

from crypto_intel.llm_client import Gateway, _extract_json
from crypto_intel.ledger import Ledger


def _resp(payload: dict[str, Any], status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


@pytest.mark.asyncio
async def test_ask_records_to_ledger(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "l.sqlite")
    body = {
        "choices": [{"message": {"content": "hello"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    transport = httpx.MockTransport(lambda req: _resp(body))
    http = httpx.AsyncClient(transport=transport)
    gw = Gateway("http://x", "k", "m", http=http, ledger=ledger)

    out = await gw.ask([{"role": "user", "content": "hi"}], tag="intel", ref="r")
    assert out == "hello"
    assert ledger.total_tokens() == 15
    assert ledger.by_tag() == [("intel", 1, 15)]
    await gw.close()


@pytest.mark.asyncio
async def test_ask_json_extracts_embedded_object(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "l.sqlite")
    body = {
        "choices": [{"message": {"content": 'ok: {"threat_score": 55, "signal": "AMBER"} end'}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    transport = httpx.MockTransport(lambda req: _resp(body))
    http = httpx.AsyncClient(transport=transport)
    gw = Gateway("http://x", "k", "m", http=http, ledger=ledger)

    data = await gw.ask_json([{"role": "user", "content": "?"}], tag="intel")
    assert data == {"threat_score": 55, "signal": "AMBER"}
    await gw.close()


@pytest.mark.asyncio
async def test_ask_json_returns_raw_on_garbage(tmp_path: Path) -> None:
    body = {
        "choices": [{"message": {"content": "not json at all"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    transport = httpx.MockTransport(lambda req: _resp(body))
    http = httpx.AsyncClient(transport=transport)
    gw = Gateway("http://x", "k", "m", http=http, ledger=Ledger(tmp_path / "l.sqlite"))

    data = await gw.ask_json([{"role": "user", "content": "?"}])
    assert "_raw" in data
    await gw.close()


def test_extract_json_pure() -> None:
    assert _extract_json('{"a":1}') == {"a": 1}
    assert _extract_json('Sure: {"b":2} done.') == {"b": 2}
    assert "_raw" in _extract_json("no json")
