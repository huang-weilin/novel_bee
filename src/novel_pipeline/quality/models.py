"""Data contracts for the quality gate."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    BLOCKER = "blocker"
    MAJOR = "major"
    MINOR = "minor"


class Decision(str, Enum):
    ACCEPT = "accept"
    POLISH = "polish"
    REWRITE = "rewrite"
    HUMAN_REVIEW = "human_review"


@dataclass(frozen=True)
class ChapterInput:
    content: str
    project_id: str = ""
    chapter_seq: int = 0
    genre: str = ""
    outline: str = ""
    character_brief: str = ""
    style_constraints: str = ""
    target_words: int = 0

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> ChapterInput:
        """Accept Mo-Shen-style payloads without coupling to their schema."""
        content = (
            data.get("content")
            or data.get("chapter")
            or data.get("final_manuscript")
            or data.get("manuscript")
            or ""
        )
        return cls(
            content=str(content),
            project_id=str(data.get("project_id", "")),
            chapter_seq=int(data.get("chapter_seq", 0) or 0),
            genre=str(data.get("genre", "")),
            outline=str(data.get("outline", "")),
            character_brief=str(data.get("character_brief", "")),
            style_constraints=str(data.get("style_constraints", "")),
            target_words=int(data.get("target_words", 0) or 0),
        )


@dataclass(frozen=True)
class RuleFinding:
    rule_id: str
    severity: Severity
    evidence: str
    suggestion: str = ""
    metrics: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "evidence": self.evidence,
            "suggestion": self.suggestion,
            "metrics": self.metrics,
        }


@dataclass
class QualityReport:
    passed: bool
    decision: Decision
    failures: list[RuleFinding] = field(default_factory=list)
    score: int | None = None
    dimensions: dict[str, int] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pass": self.passed,
            "score": self.score,
            "decision": self.decision.value,
            "dimensions": dict(self.dimensions),
            "reasons": dict(self.reasons),
            "failures": [finding.to_dict() for finding in self.failures],
            "notes": list(self.notes),
        }
