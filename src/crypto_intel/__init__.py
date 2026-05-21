"""crypto-intel — multi-strategy crypto intelligence system.

Hub-and-spoke architecture:

    Coordinator
        ├── HunterAgent   (deterministic — token discovery)
        ├── VerifyAgent   (deterministic — onchain checks)
        ├── IntelAgent    (LLM — threat & opportunity analysis)
        └── BriefAgent    (LLM — intelligence briefing)

Each agent produces a typed Pydantic contract consumed by the next
stage.  The LLM agents never see raw API payloads — only the
structured facts emitted by the deterministic agents — so they are
constrained to *reason*, not *invent*.
"""

__version__ = "1.0.0"
