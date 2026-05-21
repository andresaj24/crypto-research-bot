"""CLI — entry point for the crypto-intel system.

Commands:
    scan     — run the full pipeline against a single target
    watch    — start the autonomous watchdog loop
    intel    — show token-usage intelligence from the ledger
    summary  — generate a daily markdown summary
    probe    — quick deterministic-only smoke test (no LLM)
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from .alerter import Alerter
from .config import load_env
from .coordinator import Coordinator
from .ledger import Ledger
from .summary import render_summary, write_summary
from .watchdog import (
    Watchdog,
    WatchConfig,
    attach_signals,
    builtin_targets,
    init_logging,
    load_targets,
)

con = Console()

_DB = Path("storage/ledger.sqlite")
_OUT = Path("output")


@click.group()
@click.version_option(package_name="crypto-research-bot")
def app() -> None:
    """cri — crypto intelligence system."""


# ── scan ─────────────────────────────────────────────────────────────

@app.command()
@click.argument("target")
@click.option("-k", "--top-k", default=1, show_default=True, help="Max targets per seed.")
@click.option("-s", "--strategy", default="auto", show_default=True,
              type=click.Choice(["auto", "address", "search", "volume_spike", "fresh_pool"]))
@click.option("--save", type=click.Path(path_type=Path), default=None)
@click.option("--telegram/--no-telegram", default=True, show_default=True)
@click.option("--db", type=click.Path(path_type=Path), default=_DB, show_default=True)
def scan(
    target: str,
    top_k: int,
    strategy: str,
    save: Optional[Path],
    telegram: bool,
    db: Path,
) -> None:
    """Run the intelligence pipeline against TARGET."""
    asyncio.run(_scan(target, top_k, strategy, save, telegram, db))


async def _scan(
    target: str,
    top_k: int,
    strategy: str,
    save: Optional[Path],
    telegram: bool,
    db: Path,
) -> None:
    env = load_env()
    ledger = Ledger(db)
    alerter = Alerter(env.tg_token, env.tg_chat)
    try:
        async with Coordinator.build(env, ledger=ledger) as coord:
            con.print(f"[bold cyan]>>>[/] scanning {target!r} strategy={strategy}")
            briefs = await coord.execute(target, top_k=top_k, strategy=strategy)

        if not briefs:
            con.print("[yellow]No targets found.[/]")
            sys.exit(2)

        for b in briefs:
            con.print(Panel(
                Markdown(b.briefing_md),
                title=f"{b.target.ticker} — {b.assessment.signal.value}",
                border_style="cyan",
            ))
            if save:
                save.parent.mkdir(parents=True, exist_ok=True)
                save.write_text(b.briefing_md, encoding="utf-8")
                con.print(f"[green]saved[/] {save}")
            if telegram and alerter.active:
                ok = await alerter.push(b.briefing_md)
                con.print("[green]telegram sent[/]" if ok else "[red]telegram failed[/]")

        con.print(
            f"[dim]tokens today: {ledger.tokens_today():,} "
            f"| lifetime: {ledger.total_tokens():,}[/]"
        )
    finally:
        await alerter.close()


# ── watch ────────────────────────────────────────────────────────────

@app.command()
@click.option("--targets", type=click.Path(path_type=Path), default=None,
              help="Target list file.  Falls back to built-in list.")
@click.option("--cycle-pause", type=float, default=60.0, show_default=True)
@click.option("--seed-pause", type=float, default=5.0, show_default=True)
@click.option("--max-cycles", type=int, default=None)
@click.option("--brief-dir", type=click.Path(path_type=Path),
              default=Path("output/briefs"), show_default=True)
@click.option("--db", type=click.Path(path_type=Path), default=_DB, show_default=True)
@click.option("--debug", is_flag=True)
def watch(
    targets: Optional[Path],
    cycle_pause: float,
    seed_pause: float,
    max_cycles: Optional[int],
    brief_dir: Path,
    db: Path,
    debug: bool,
) -> None:
    """Start the autonomous watchdog loop."""
    init_logging(debug=debug)
    env = load_env()
    ledger = Ledger(db)

    target_list = load_targets(targets) if targets else list(builtin_targets())

    cfg = WatchConfig(
        targets=target_list,
        cycle_pause=cycle_pause,
        seed_pause=seed_pause,
        max_cycles=max_cycles,
        brief_dir=brief_dir,
    )
    wd = Watchdog(env=env, cfg=cfg, ledger=ledger)

    async def _run() -> None:
        attach_signals(wd)
        await wd.run()

    asyncio.run(_run())


# ── intel ────────────────────────────────────────────────────────────

@app.command()
@click.option("--db", type=click.Path(path_type=Path), default=_DB, show_default=True)
def intel(db: Path) -> None:
    """Show token-usage intelligence from the ledger."""
    ledger = Ledger(db)

    model = None
    try:
        model = load_env().llm_model
    except Exception:
        pass

    t = Table(title="Ledger Overview", show_header=True, header_style="bold cyan")
    t.add_column("Metric", style="dim")
    t.add_column("Value", justify="right")
    t.add_row("Today (UTC)", f"{ledger.tokens_today():,}")
    t.add_row("Lifetime", f"{ledger.total_tokens():,}")
    t.add_row("Missions", f"{ledger.mission_count():,}")
    if model:
        t.add_row("Model", model)
    con.print(t)

    tags = ledger.by_tag()
    if tags:
        at = Table(title="By Agent", show_header=True, header_style="bold cyan")
        at.add_column("Agent")
        at.add_column("Calls", justify="right")
        at.add_column("Tokens", justify="right")
        for tag, calls, tokens in tags:
            at.add_row(tag, f"{calls:,}", f"{tokens:,}")
        con.print(at)

    hm = ledger.daily_heatmap(days=7)
    if hm:
        ht = Table(title="7-Day Heatmap", show_header=True, header_style="bold cyan")
        ht.add_column("Date")
        ht.add_column("Calls", justify="right")
        ht.add_column("Tokens", justify="right")
        for day, calls, tokens in hm:
            ht.add_row(day, f"{calls:,}", f"{tokens:,}")
        con.print(ht)


# ── summary ──────────────────────────────────────────────────────────

@app.command()
@click.option("--db", type=click.Path(path_type=Path), default=_DB, show_default=True)
@click.option("--out-dir", type=click.Path(path_type=Path), default=_OUT, show_default=True)
@click.option("--telegram/--no-telegram", default=False, show_default=True)
def summary(db: Path, out_dir: Path, telegram: bool) -> None:
    """Generate a daily intelligence summary."""
    ledger = Ledger(db)
    model = None
    try:
        model = load_env().llm_model
    except Exception:
        pass

    text = render_summary(ledger, model=model)
    con.print(Markdown(text))

    path = write_summary(ledger, out_dir, model=model)
    con.print(f"[green]saved[/] {path}")

    if telegram:
        asyncio.run(_push_summary(text))


async def _push_summary(text: str) -> None:
    env = load_env()
    alerter = Alerter(env.tg_token, env.tg_chat)
    try:
        if not alerter.active:
            con.print("[yellow]telegram not configured[/]")
            return
        ok = await alerter.push(text)
        con.print("[green]telegram sent[/]" if ok else "[red]telegram failed[/]")
    finally:
        await alerter.close()


# ── probe ────────────────────────────────────────────────────────────

@app.command()
@click.option("--strategy", default="auto", show_default=True,
              type=click.Choice(["auto", "address", "search", "volume_spike", "fresh_pool"]))
def probe(strategy: str) -> None:
    """Quick deterministic-only smoke test — no LLM, no API keys needed."""
    seed = "0x6982508145454ce325ddbe47a25d4ec3d2311933"  # PEPE
    asyncio.run(_probe(seed, strategy))


async def _probe(seed: str, strategy: str) -> None:
    from .agents.hunter import HunterAgent

    h = HunterAgent()
    try:
        targets = await h.hunt(seed, top_k=3, strategy=strategy)
    finally:
        await h.close()

    if not targets:
        con.print("[yellow]No targets found.[/]")
        return

    t = Table(title=f"Probe — {seed!r} strategy={strategy}")
    for col in ("Network", "Ticker", "Liquidity", "24h Vol", "FDV", "Strategy"):
        t.add_column(col)
    for tgt in targets:
        t.add_row(
            tgt.network,
            tgt.ticker,
            f"${(tgt.pool_liquidity or 0):,.0f}",
            f"${(tgt.day_volume or 0):,.0f}",
            f"${(tgt.fully_diluted_val or 0):,.0f}",
            tgt.hunt_strategy,
        )
    con.print(t)


if __name__ == "__main__":
    app()
