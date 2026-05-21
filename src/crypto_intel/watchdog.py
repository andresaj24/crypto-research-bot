"""Watchdog — autonomous monitoring loop.

Cycles through a target list, executing the full Coordinator pipeline
for each entry, sleeping between seeds and between cycles.

Gracefully handles SIGINT / SIGTERM for clean shutdown.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

from .config import Env
from .coordinator import Coordinator
from .ledger import Ledger


log = logging.getLogger("crypto_intel.watchdog")


@dataclass
class WatchConfig:
    targets: list[str]
    cycle_pause: float = 60.0
    seed_pause: float = 5.0
    max_cycles: Optional[int] = None
    brief_dir: Optional[Path] = None
    on_brief: Optional[Callable] = None  # type: ignore[type-arg]


def load_targets(path: Path) -> list[str]:
    """One target per line.  Blank lines and ``#`` comments are skipped."""
    if not path.exists():
        raise FileNotFoundError(f"target file not found: {path}")
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            out.append(s)
    if not out:
        raise ValueError(f"target file is empty: {path}")
    return out


class Watchdog:
    """Long-running monitoring loop."""

    def __init__(self, env: Env, cfg: WatchConfig, ledger: Ledger) -> None:
        self.env = env
        self.cfg = cfg
        self.ledger = ledger
        self._halt = asyncio.Event()

    def stop(self) -> None:
        self._halt.set()

    async def run(self) -> None:
        targets = list(self.cfg.targets)
        if not targets:
            log.warning("no targets — watchdog exiting")
            return

        log.info("watchdog starting | targets=%d pause=%.0fs", len(targets), self.cfg.cycle_pause)
        cycle = 0

        async with Coordinator.build(self.env, ledger=self.ledger) as coord:
            while not self._halt.is_set():
                cycle += 1
                log.info("── cycle %d ──", cycle)
                for seed in targets:
                    if self._halt.is_set():
                        break
                    try:
                        briefs = await coord.execute(seed, top_k=1)
                    except Exception as exc:  # noqa: BLE001
                        log.exception("seed %s failed: %s", seed, exc)
                        continue

                    for b in briefs:
                        log.info(
                            "  %s/%s signal=%s threat=%d tokens_today=%s",
                            b.target.network,
                            b.target.ticker,
                            b.assessment.signal.value,
                            b.assessment.threat_score,
                            f"{self.ledger.tokens_today():,}",
                        )
                        if self.cfg.brief_dir is not None:
                            _persist(self.cfg.brief_dir, b)
                        if self.cfg.on_brief is not None:
                            try:
                                await _maybe_await(self.cfg.on_brief(b))
                            except Exception:  # noqa: BLE001
                                log.exception("on_brief callback failed")

                    await self._pause(self.cfg.seed_pause)

                if self.cfg.max_cycles is not None and cycle >= self.cfg.max_cycles:
                    log.info("max_cycles reached — stopping")
                    return

                await self._pause(self.cfg.cycle_pause)

        log.info("watchdog stopped")

    async def _pause(self, seconds: float) -> None:
        if seconds <= 0 or self._halt.is_set():
            return
        try:
            await asyncio.wait_for(self._halt.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass


def _persist(directory: Path, brief) -> None:  # type: ignore[no-untyped-def]
    directory.mkdir(parents=True, exist_ok=True)
    ts = brief.produced_at.strftime("%Y%m%dT%H%M%SZ")
    safe = "".join(c if c.isalnum() else "_" for c in brief.target.ticker)[:24]
    out = directory / f"{ts}_{safe}_{brief.target.network}.md"
    out.write_text(brief.briefing_md, encoding="utf-8")


async def _maybe_await(val):  # type: ignore[no-untyped-def]
    if asyncio.iscoroutine(val):
        return await val
    return val


def attach_signals(wd: Watchdog) -> None:
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, wd.stop)
        except NotImplementedError:
            pass


def init_logging(debug: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def builtin_targets() -> Iterable[str]:
    """Default watchlist when --targets isn't given."""
    return [
        "0x6982508145454ce325ddbe47a25d4ec3d2311933",  # PEPE
        "0x95aD61b0a150d79219dCF64E1E6Cc01f0B64C4cE",  # SHIB
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",  # USDC
        "0x4ed4e862860bed51a9570b96d89af5e1b0efefed",  # DEGEN (Base)
        "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",  # WBNB (BSC)
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC (Solana)
        "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",  # BONK (Solana)
        "WIF",
        "JUP",
    ]
