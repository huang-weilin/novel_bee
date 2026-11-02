"""Quality-layer adapter.

M2 starts with a log-only shell; the rule-engine mode is already wired so
Mo-Shen's chapter output can be intercepted without modifying its source.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping

from .models import ChapterInput, Decision, QualityReport, Severity
from .rules import RuleEngine
from .scorer import LLMScorer
from .verifier import LLMVerifier

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {Severity.BLOCKER: 0, Severity.MAJOR: 1, Severity.MINOR: 2}


class QualityAdapter:
    def __init__(
        self,
        engine: RuleEngine | None = None,
        verifier: LLMVerifier | None = None,
        scorer: LLMScorer | None = None,
        log: logging.Logger | None = None,
    ):
        self.engine = engine or RuleEngine()
        self.verifier = verifier
        self.scorer = scorer
        self.log = log or logger

    def review(
        self,
        chapter: ChapterInput | Mapping,
        *,
        mode: str = "rules",
    ) -> QualityReport:
        """Review one chapter.

        ``mode='log_only'`` implements the T2-1 shell: record and pass through.
        ``mode='rules'`` runs Q01-Q06 plus Q11/Q12; ``mode='rules+llm'`` also runs Q07-Q10;
        ``mode='full'`` adds the four-dimension scorer. A verifier/scorer
        failure goes to human_review. Full mode applies the SPEC decision
        thresholds; rule-only modes keep an interim mapping.
        """
        if isinstance(chapter, Mapping):
            chapter = ChapterInput.from_mapping(chapter)

        if mode == "log_only":
            report = QualityReport(
                passed=True,
                decision=Decision.ACCEPT,
                notes=["log_only"],
            )
        elif mode in ("rules", "rules+llm", "rules+score", "full"):
            findings = self.engine.check(
                chapter.content,
                genre=chapter.genre,
                target_words=chapter.target_words,
            )
            notes = (
                ["rules_only_no_scoring"]
                if mode in ("rules", "rules+llm")
                else []
            )
            score: int | None = None
            dimensions: dict[str, int] = {}
            reasons: dict[str, str] = {}

            if mode in ("rules+llm", "full"):
                if self.verifier is None:
                    raise ValueError(f"{mode} mode requires a verifier")
                result = self.verifier.verify(chapter)
                findings.extend(result.findings)
                if result.human_review:
                    report = self._human_review_report(
                        chapter, findings, notes + [f"verifier_error: {result.error}"]
                    )
                    return report
                notes.append("verifier_ok")

            if mode in ("rules+score", "full"):
                if self.scorer is None:
                    raise ValueError(f"{mode} mode requires a scorer")
                result = self.scorer.score(chapter)
                if result.human_review:
                    report = self._human_review_report(
                        chapter, findings, notes + [f"scorer_error: {result.error}"]
                    )
                    return report
                score = result.score
                dimensions = result.dimensions
                reasons = result.reasons
                notes.append("scored")

            has_blocker = any(finding.severity is Severity.BLOCKER for finding in findings)
            has_major = any(finding.severity is Severity.MAJOR for finding in findings)
            if has_blocker or (score is not None and score < 55):
                decision = Decision.REWRITE
            elif score is not None:
                decision = (
                    Decision.ACCEPT
                    if score >= 75 and not has_major
                    else Decision.POLISH
                )
            elif has_major:
                decision = Decision.POLISH
            else:
                decision = Decision.ACCEPT

            report = QualityReport(
                passed=decision is Decision.ACCEPT,
                decision=decision,
                failures=sorted(
                    findings, key=lambda item: _SEVERITY_ORDER[item.severity]
                ),
                score=score,
                dimensions=dimensions,
                reasons=reasons,
                notes=notes,
            )
        else:
            raise ValueError(f"unknown quality mode: {mode!r}")

        self.log.info(
            "quality_review %s",
            json.dumps(self._log_record(chapter, report), ensure_ascii=False),
        )
        return report

    def _human_review_report(
        self,
        chapter: ChapterInput,
        findings: list,
        notes: list[str],
    ) -> QualityReport:
        report = QualityReport(
            passed=False,
            decision=Decision.HUMAN_REVIEW,
            failures=sorted(
                findings, key=lambda item: _SEVERITY_ORDER[item.severity]
            ),
            notes=notes,
        )
        self.log.info(
            "quality_review %s",
            json.dumps(self._log_record(chapter, report), ensure_ascii=False),
        )
        return report

    @staticmethod
    def _log_record(chapter: ChapterInput, report: QualityReport) -> dict:
        digest = hashlib.sha256(chapter.content.encode("utf-8")).hexdigest()[:12]
        return {
            "project_id": chapter.project_id,
            "chapter_seq": chapter.chapter_seq,
            "genre": chapter.genre,
            "chars": len(chapter.content),
            "sha256_12": digest,
            "decision": report.decision.value,
            "passed": report.passed,
            "score": report.score,
            "rule_ids": [finding.rule_id for finding in report.failures],
        }
