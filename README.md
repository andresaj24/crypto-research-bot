# crypto-research-bot

**Multi-Strategy Crypto Intelligence System — Autonomous Scanning, Onchain Verification, LLM-Powered Threat Analysis & BLUF Briefings**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## Overview

`crypto-research-bot` is an autonomous intelligence system that continuously scans decentralised exchanges, verifies onchain data, and generates structured threat assessments for crypto tokens.  It uses a **hub-and-spoke** architecture where a central Coordinator dispatches work to four specialist agents:

| # | Agent | Type | Role |
|---|---|---|---|
| 1 | **HunterAgent** | deterministic | Multi-strategy token discovery via DexScreener — supports address lookup, free-text search, volume-spike detection, and fresh-pool filtering. |
| 2 | **VerifyAgent** | deterministic | Onchain fact-checking via Etherscan v2 multichain API (EVM) and Solana RPC.  Checks source-code verification, SPL programme ownership, account existence. |
| 3 | **IntelAgent** | LLM | Dual-axis threat/opportunity analysis with confidence scoring.  Walks through seven intelligence dimensions before emitting a GREEN / AMBER / RED signal. |
| 4 | **BriefAgent** | LLM | Produces BLUF (Bottom Line Up Front) intelligence briefs in markdown — clinical, evidence-led, never recommends buy/sell. |

The deterministic agents gather **verified facts**; the LLM agents reason over those facts.  Every LLM call is logged to a SQLite ledger for full auditability.

---

## Architecture

```
                   Hub-and-Spoke Intelligence Pipeline

  seed (address / symbol / query + strategy)
       │
       ▼
  ┌──────────────┐
  │  Coordinator  │ ◄── dispatches & records missions
  └──────┬───────┘
         │
    ┌────┼───────────────────────────────────┐
    │    │                                   │
    ▼    ▼                                   │
  HunterAgent        VerifyAgent             │
  (DexScreener)      (Etherscan / Sol RPC)   │
    │ TokenTarget       │ ChainIntel         │
    └────────┬──────────┘                    │
             ▼                               │
        IntelAgent  ◄── LLM                  │
        (7-dimension analysis)               │
             │ ThreatAssessment              │
             ▼                               │
        BriefAgent  ◄── LLM                  │
        (BLUF markdown)                      │
             │ IntelBrief                    │
             └───────────────────────────────┘
                         │
                         ▼
                   output / Telegram
```

---

## Hunting Strategies

The HunterAgent supports multiple discovery strategies:

| Strategy | Behaviour |
|----------|-----------|
| `auto` | Detects whether the seed is an address (EVM / Solana) or a search query and routes accordingly. |
| `address` | Direct token lookup by contract / mint address. |
| `search` | Free-text DexScreener search across all chains. |
| `volume_spike` | Search then filter: only tokens where 24h volume >= 2x pool liquidity. |
| `fresh_pool` | Search then filter: only pairs younger than 48 hours. |

---

## Signal Classification

Instead of a simple low/medium/high risk label the system uses a dual-axis model:

| Signal | Meaning |
|--------|---------|
| **GREEN** | Low threat, reasonable opportunity — relatively safe for further research. |
| **AMBER** | Mixed signals — some concerning indicators, investigate further. |
| **RED** | High threat — significant rug-pull / honeypot / concentration risk. |

Each assessment also carries a **confidence percentage** so downstream consumers can weight the result.

---

## Quick Start

```bash
git clone https://github.com/andresaj24/crypto-research-bot.git
cd crypto-research-bot
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # configure your LLM provider

# Smoke test — deterministic only, no LLM / API keys needed
cri probe

# Full intelligence scan on a single target
cri scan 0x6982508145454ce325ddbe47a25d4ec3d2311933

# Scan with a specific strategy
cri scan PEPE --strategy volume_spike

# Start the autonomous watchdog loop
cri watch

# Finite run with custom targets
cri watch --targets seeds/watchlist.txt --max-cycles 3

# View ledger stats
cri intel

# Generate daily summary
cri summary --telegram
```

---

## Configuration

All settings live in `.env` (or process environment):

```bash
# ── LLM (required) ───────────────────────────
# Any OpenAI-compatible endpoint.
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=your-key
LLM_MODEL=nousresearch/hermes-3-llama-3.1-8b

# ── Onchain (optional) ───────────────────────
ETHERSCAN_API_KEY=
SOLANA_RPC_URL=

# ── Telegram (optional) ──────────────────────
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

Supported LLM providers: **OpenRouter**, **OpenAI**, **Together AI**, **Gemini**, **DeepSeek**, local **vLLM** / **llama.cpp**, or anything else that speaks the OpenAI Chat Completions API.

---

## Project Layout

```
crypto-research-bot/
├── src/crypto_intel/
│   ├── cli.py              # `cri` CLI (Click + Rich)
│   ├── config.py           # .env loader → Env dataclass
│   ├── llm_client.py       # Gateway — LLM wrapper with retry & ledger
│   ├── ledger.py           # SQLite ledger (calls + missions)
│   ├── dex.py              # DexScreener gateway
│   ├── coordinator.py      # Hub-and-spoke pipeline orchestrator
│   ├── watchdog.py         # Autonomous monitoring loop
│   ├── summary.py          # Daily summary renderer
│   ├── alerter.py          # Telegram alerter
│   ├── models.py           # Pydantic contracts (TokenTarget, ChainIntel, …)
│   └── agents/
│       ├── hunter.py       # Multi-strategy discovery
│       ├── verify.py       # Etherscan + Solana verification
│       ├── intel.py        # LLM threat/opportunity analysis
│       └── brief.py        # LLM BLUF briefing writer
├── seeds/watchlist.txt     # Default watchdog target list
├── tests/                  # Fully mocked — no network or LLM calls
└── storage/                # SQLite ledger (gitignored)
```

---

## Testing

```bash
pytest -q
```

All tests use mocked HTTP transports — zero network or LLM calls.

---

## Roadmap

- [x] Hub-and-spoke pipeline (Hunter / Verify / Intel / Brief)
- [x] Multi-strategy hunting (address, search, volume_spike, fresh_pool)
- [x] Dual-axis threat + opportunity scoring with confidence
- [x] GREEN / AMBER / RED signal classification
- [x] BLUF intelligence briefing format
- [x] SQLite ledger with mission tracking
- [x] Autonomous watchdog with graceful shutdown
- [x] Telegram alerting
- [x] Solana RPC support
- [ ] Web dashboard (live ledger + heatmaps)
- [ ] Holder concentration agent (top-N via Etherscan logs)
- [ ] Cross-chain flow analysis
- [ ] Historical backtest against known rug-pulls
- [ ] Webhook integrations (Discord, Slack)

---

## License

MIT — see [LICENSE](LICENSE).

---

**Built by [@andresaj24](https://github.com/andresaj24)**
