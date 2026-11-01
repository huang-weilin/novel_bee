"""Decision and retry loop.

The loop is deliberately decoupled from generation: callers provide a review
function and a revision function. This keeps the quality gate testable and
lets M4 wire in the actual rewrite/polish prompts.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace

from .models import ChapterInput, Decision, QualityReport, RuleFinding

DEFAULT_MAX_REWRITES = 3
DEFAULT_MAX_POLISH = 2


@dataclass(frozen=True)
class RevisionRequest:
    action: Decision
    attempt: int
    failures: tuple[RuleFinding, ...]
    score: int | None
    dimensions: dict[str, int]
    reason: str

    def to_dict(self) -> dict:
        return {
            "action": self.action.value,
            "attempt": self.attempt,
            "failures": [finding.to_dict() for finding in self.failures],
            "score": self.score,
            "dimensions": dict(self.dimensions),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class LoopAttempt:
    attempt: int
    decision: str
    score: int | None
    rule_ids: tuple[str, ...]
    action: str

    def to_dict(self) -> dict:
        return {
            "attempt": self.attempt,
            "decision": self.decision,
            "score": self.score,
            "rule_ids": list(self.rule_ids),
            "action": self.action,
        }


@dataclass
class QualityLoopResult:
    chapter: ChapterInput
    report: QualityReport
    attempts: list[LoopAttempt] = field(default_factory=list)
    rewrite_count: int = 0
    polish_count: int = 0
    stopped_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "chapter": {
                "project_id": self.chapter.project_id,
                "chapter_seq": self.chapter.chapter_seq,
                "chars": len(self.chapter.content),
            },
            "report": self.report.to_dict(),
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "rewrite_count": self.rewrite_count,
            "polish_count": self.polish_count,
            "stopped_reason": self.stopped_reason,
        }


class QualityLoop:
    def __init__(
        self,
        max_rewrites: int = DEFAULT_MAX_REWRITES,
        max_polish: int = DEFAULT_MAX_POLISH,
    ):
        if max_rewrites < 0 or max_polish < 0:
            raise ValueError("retry limits must be non-negative")
        self.max_rewrites = max_rewrites
        self.max_polish = max_polish

    def run(
        self,
        chapter: ChapterInput,
        review: Callable[[ChapterInput], QualityReport],
        revise: Callable[[ChapterInput, RevisionRequest], ChapterInput],
    ) -> QualityLoopResult:
        current = chapter
        attempts: list[LoopAttempt] = []
        rewrite_count = 0
        polish_count = 0

        for attempt_index in range(1, self.max_rewrites + self.max_polish + 2):
            report = review(current)
            action = "stop"
            if report.decision is Decision.ACCEPT:
                attempts.append(
                    self._attempt(attempt_index, report, "accept")
                )
                return QualityLoopResult(
                    chapter=current,
                    report=report,
                    attempts=attempts,
                    rewrite_count=rewrite_count,
                    polish_count=polish_count,
                    stopped_reason="accept",
                )
            if report.decision is Decision.HUMAN_REVIEW:
                attempts.append(
                    self._attempt(attempt_index, report, "human_review")
                )
                return QualityLoopResult(
                    chapter=current,
                    report=report,
                    attempts=attempts,
                    rewrite_count=rewrite_count,
                    polish_count=polish_count,
                    stopped_reason="human_review",
                )

            if report.decision is Decision.REWRITE:
                if rewrite_count >= self.max_rewrites:
                    attempts.append(
                        self._attempt(attempt_index, report, "rewrite_limit")
                    )
                    return self._stop(
                        current,
                        report,
                        attempts,
                        rewrite_count,
                        polish_count,
                        "rewrite_limit",
                    )
                rewrite_count += 1
                action = "rewrite"
            elif report.decision is Decision.POLISH:
                if polish_count >= self.max_polish:
                    attempts.append(
                        self._attempt(attempt_index, report, "polish_limit")
                    )
                    return self._stop(
                        current,
                        report,
                        attempts,
                        rewrite_count,
                        polish_count,
                        "polish_limit",
                    )
                polish_count += 1
                action = "polish"
            else:  # pragma: no cover - Decision is a closed set
                attempts.append(
                    self._attempt(attempt_index, report, "unknown_decision")
                )
                return self._stop(
                    current,
                    report,
                    attempts,
                    rewrite_count,
                    polish_count,
                    "unknown_decision",
                )

            attempts.append(self._attempt(attempt_index, report, action))
            request = RevisionRequest(
                action=report.decision,
                attempt=rewrite_count + polish_count,
                failures=tuple(report.failures),
                score=report.score,
                dimensions=dict(report.dimensions),
                reason=self._reason(report),
            )
            try:
                next_chapter = revise(current, request)
                if not isinstance(next_chapter, ChapterInput):
                    raise TypeError("revise() must return ChapterInput")
            except Exception as exc:  # noqa: BLE001 - revision failure must not crash the loop
                return self._stop(
                    current,
                    report,
                    attempts,
                    rewrite_count,
                    polish_count,
                    f"revision_error: {exc}",
                )
            current = next_chapter

        return self._stop(
            current,
            report,
            attempts,
            rewrite_count,
            polish_count,
            "max_attempts",
        )

    @staticmethod
    def _attempt(attempt: int, report: QualityReport, action: str) -> LoopAttempt:
        return LoopAttempt(
            attempt=attempt,
            decision=report.decision.value,
            score=report.score,
            rule_ids=tuple(finding.rule_id for finding in report.failures),
            action=action,
        )

    @staticmethod
    def _reason(report: QualityReport) -> str:
        blockers = [
            finding.rule_id
            for finding in report.failures
            if finding.severity.value == "blocker"
        ]
        if blockers:
            return f"blocker: {', '.join(blockers)}"
        if report.score is not None:
            return f"score: {report.score}"
        return "rule findings"

    def _stop(
        self,
        chapter: ChapterInput,
        report: QualityReport,
        attempts: list[LoopAttempt],
        rewrite_count: int,
        polish_count: int,
        reason: str,
    ) -> QualityLoopResult:
        final = replace(
            report,
            passed=False,
            decision=Decision.HUMAN_REVIEW,
            notes=list(report.notes) + [f"stopped: {reason}"],
        )
        return QualityLoopResult(
            chapter=chapter,
            report=final,
            attempts=attempts,
            rewrite_count=rewrite_count,
            polish_count=polish_count,
            stopped_reason=reason,
        )
