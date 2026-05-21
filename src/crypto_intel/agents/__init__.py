"""Agent package — four specialist agents wired by the Coordinator."""

from .hunter import HunterAgent
from .verify import VerifyAgent
from .intel import IntelAgent
from .brief import BriefAgent

__all__ = ["HunterAgent", "VerifyAgent", "IntelAgent", "BriefAgent"]
