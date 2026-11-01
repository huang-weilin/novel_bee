"""Quality gate: programmatic rules, LLM verifier, and scoring."""

from .adapter import QualityAdapter
from .loop import (
    QualityLoop,
    QualityLoopResult,
    RevisionRequest,
)
from .models import ChapterInput, Decision, QualityReport, RuleFinding, Severity
from .reviser import LLMReviser, RevisionError
from .rules import RuleEngine

__all__ = [
    "ChapterInput",
    "Decision",
    "LLMReviser",
    "QualityAdapter",
    "QualityLoop",
    "QualityLoopResult",
    "QualityReport",
    "RevisionError",
    "RevisionRequest",
    "RuleEngine",
    "RuleFinding",
    "Severity",
]
