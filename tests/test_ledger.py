"""Tests for the SQLite ledger."""

from pathlib import Path

from crypto_intel.ledger import Ledger


def test_log_calls_and_aggregate(tmp_path: Path) -> None:
    db = tmp_path / "l.sqlite"
    led = Ledger(db)

    led.log_call(tag="intel", model="m", prompt_tok=100, gen_tok=50, ref="s1")
    led.log_call(tag="intel", model="m", prompt_tok=80, gen_tok=20, ref="s1")
    led.log_call(tag="brief", model="m", prompt_tok=200, gen_tok=100, ref="s1")

    assert led.total_tokens() == 100 + 50 + 80 + 20 + 200 + 100
    assert led.tokens_today() == led.total_tokens()

    by_tag = {t: (c, tok) for t, c, tok in led.by_tag()}
    assert by_tag["intel"] == (2, 250)
    assert by_tag["brief"] == (1, 300)


def test_missions(tmp_path: Path) -> None:
    led = Ledger(tmp_path / "l.sqlite")
    led.log_mission(
        ref="0xdead",
        network="ethereum",
        contract="0xdead",
        ticker="DEAD",
        threat=42,
        signal="AMBER",
        tokens_used=1234,
        ms=5678,
    )
    assert led.mission_count() == 1
    recent = led.recent_missions(n=5)
    assert recent[0]["ticker"] == "DEAD"
    assert recent[0]["threat"] == 42
    assert recent[0]["signal"] == "AMBER"


def test_empty_ledger(tmp_path: Path) -> None:
    led = Ledger(tmp_path / "empty.sqlite")
    assert led.total_tokens() == 0
    assert led.tokens_today() == 0
    assert led.mission_count() == 0
    assert led.by_tag() == []
    assert led.daily_heatmap() == []
    assert led.recent_missions() == []
