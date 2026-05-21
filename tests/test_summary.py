"""Tests for the daily summary renderer."""

from pathlib import Path

from crypto_intel.summary import render_summary, write_summary
from crypto_intel.ledger import Ledger


def test_render_with_data(tmp_path: Path) -> None:
    led = Ledger(tmp_path / "l.sqlite")
    led.log_call(tag="intel", model="m", prompt_tok=100, gen_tok=50)
    led.log_call(tag="brief", model="m", prompt_tok=300, gen_tok=200)
    led.log_mission(
        ref="PEPE",
        network="ethereum",
        contract="0xpepe",
        ticker="PEPE",
        threat=33,
        signal="AMBER",
        tokens_used=650,
        ms=12000,
    )
    text = render_summary(led, model="hermes-3-llama-3.1-8b")
    assert "Intelligence Summary" in text
    assert "650" in text
    assert "hermes-3-llama-3.1-8b" in text
    assert "intel" in text and "brief" in text
    assert "PEPE" in text


def test_render_empty(tmp_path: Path) -> None:
    led = Ledger(tmp_path / "l.sqlite")
    text = render_summary(led)
    assert "0 tokens" in text or "Lifetime:** 0" in text


def test_write_creates_file(tmp_path: Path) -> None:
    led = Ledger(tmp_path / "l.sqlite")
    led.log_call(tag="intel", model="m", prompt_tok=10, gen_tok=5)
    out = tmp_path / "output"
    path = write_summary(led, out)
    assert path.exists()
    assert path.name.startswith("daily_")
    assert "Intelligence Summary" in path.read_text(encoding="utf-8")
