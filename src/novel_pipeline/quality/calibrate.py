"""Calibration harness for the quality gate.

Reads a directory of chapter files (``.md`` / ``.txt``) with optional
``<stem>.json`` sidecar metadata, runs the gate, and writes a summary.
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .adapter import QualityAdapter
from .loop import QualityLoop, QualityLoopResult
from .models import ChapterInput, QualityReport
from .reviser import LLMReviser
from .scorer import LLMScorer
from .verifier import LLMVerifier

logger = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = {".md", ".txt"}
SCORE_BUCKETS = (
    ("0-39", 0, 39),
    ("40-54", 40, 54),
    ("55-74", 55, 74),
    ("75-100", 75, 100),
)


@dataclass
class CalibrationCase:
    name: str
    chapter: ChapterInput


@dataclass
class CalibrationResult:
    name: str
    decision: str
    score: int | None
    rule_ids: list[str] = field(default_factory=list)
    initial_decision: str = ""
    initial_score: int | None = None
    initial_rule_ids: list[str] = field(default_factory=list)
    rewrite_count: int = 0
    polish_count: int = 0
    stopped_reason: str = ""
    attempts: int = 0
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "decision": self.decision,
            "score": self.score,
            "rule_ids": list(self.rule_ids),
            "initial_decision": self.initial_decision or self.decision,
            "initial_score": (
                self.initial_score if self.initial_score is not None else self.score
            ),
            "initial_rule_ids": list(self.initial_rule_ids or self.rule_ids),
            "rewrite_count": self.rewrite_count,
            "polish_count": self.polish_count,
            "stopped_reason": self.stopped_reason,
            "attempts": self.attempts,
            "error": self.error,
        }


def load_cases(directory: str | Path) -> list[CalibrationCase]:
    root = Path(directory)
    if not root.is_dir():
        raise ValueError(f"calibration directory not found: {root}")
    files = sorted(
        path
        for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )
    if not files:
        raise ValueError(f"no chapter files found in {root}")

    cases: list[CalibrationCase] = []
    for path in files:
        sidecar = path.with_suffix(".json")
        meta = {}
        if sidecar.exists():
            meta = json.loads(sidecar.read_text(encoding="utf-8"))
        content = path.read_text(encoding="utf-8")
        cases.append(
            CalibrationCase(
                name=path.stem,
                chapter=ChapterInput(
                    content=content,
                    project_id=str(meta.get("project_id", path.stem)),
                    chapter_seq=int(meta.get("chapter_seq", 0) or 0),
                    genre=str(meta.get("genre", "")),
                    outline=str(meta.get("outline", "")),
                    character_brief=str(meta.get("character_brief", "")),
                    style_constraints=str(meta.get("style_constraints", "")),
                ),
            )
        )
    return cases


def result_from_report(
    name: str,
    report: QualityReport,
    loop_result: QualityLoopResult | None = None,
) -> CalibrationResult:
    final_rules = [finding.rule_id for finding in report.failures]
    if loop_result and loop_result.attempts:
        first = loop_result.attempts[0]
        initial_decision = first.decision
        initial_score = first.score
        initial_rules = list(first.rule_ids)
    else:
        initial_decision = report.decision.value
        initial_score = report.score
        initial_rules = final_rules

    return CalibrationResult(
        name=name,
        decision=report.decision.value,
        score=report.score,
        rule_ids=final_rules,
        initial_decision=initial_decision,
        initial_score=initial_score,
        initial_rule_ids=initial_rules,
        rewrite_count=loop_result.rewrite_count if loop_result else 0,
        polish_count=loop_result.polish_count if loop_result else 0,
        stopped_reason=loop_result.stopped_reason if loop_result else "review_only",
        attempts=len(loop_result.attempts) if loop_result else 1,
    )


def run_calibration(
    cases: Iterable[CalibrationCase],
    review: Callable[[ChapterInput], QualityReport],
    revise: Callable | None = None,
    loop: QualityLoop | None = None,
) -> list[CalibrationResult]:
    results: list[CalibrationResult] = []
    for case in cases:
        logger.info("calibrating %s chars=%d", case.name, len(case.chapter.content))
        try:
            if revise is not None and loop is not None:
                loop_result = loop.run(case.chapter, review, revise)
                results.append(
                    result_from_report(case.name, loop_result.report, loop_result)
                )
            else:
                results.append(
                    result_from_report(case.name, review(case.chapter))
                )
        except Exception as exc:  # one bad sample must not kill the run
            logger.exception("calibration failed for %s", case.name)
            results.append(
                CalibrationResult(
                    name=case.name,
                    decision="error",
                    score=None,
                    error=str(exc),
                )
            )
    return results


def _score_buckets(scores: list[int]) -> dict[str, int]:
    buckets = Counter()
    for score in scores:
        for label, low, high in SCORE_BUCKETS:
            if low <= score <= high:
                buckets[label] += 1
                break
    return {label: buckets.get(label, 0) for label, _, _ in SCORE_BUCKETS}


def summarize(results: Iterable[CalibrationResult]) -> dict:
    rows = list(results)
    decisions = Counter(row.decision for row in rows)
    initial_decisions = Counter(
        row.initial_decision or row.decision for row in rows
    )
    rule_hits: Counter[str] = Counter()
    for row in rows:
        rule_hits.update(row.initial_rule_ids or row.rule_ids)

    scores = [row.score for row in rows if row.score is not None]
    initial_scores = [
        row.initial_score if row.initial_score is not None else row.score
        for row in rows
    ]
    initial_scores = [score for score in initial_scores if score is not None]
    rewrites = [row.rewrite_count for row in rows]

    return {
        "chapters": len(rows),
        "initial_decisions": dict(initial_decisions),
        "decisions": dict(decisions),
        "initial_accept_rate": round(
            initial_decisions.get("accept", 0) / len(rows), 4
        )
        if rows
        else 0.0,
        "accept_rate": round(decisions.get("accept", 0) / len(rows), 4)
        if rows
        else 0.0,
        "avg_initial_score": round(statistics.fmean(initial_scores), 2)
        if initial_scores
        else None,
        "avg_score": round(statistics.fmean(scores), 2) if scores else None,
        "initial_score_buckets": _score_buckets(initial_scores),
        "score_buckets": _score_buckets(scores),
        "rule_hits": dict(rule_hits),
        "avg_rewrites": round(statistics.fmean(rewrites), 2) if rewrites else 0.0,
        "max_rewrites": max(rewrites) if rewrites else 0,
        "avg_polish": round(
            statistics.fmean([row.polish_count for row in rows]), 2
        )
        if rows
        else 0.0,
        "human_reviews": decisions.get("human_review", 0),
        "errors": decisions.get("error", 0),
    }


def make_review(adapter: QualityAdapter, mode: str) -> Callable[[ChapterInput], QualityReport]:
    def review(chapter: ChapterInput) -> QualityReport:
        return adapter.review(chapter, mode=mode)

    return review


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m novel_pipeline.quality.calibrate")
    parser.add_argument("directory", type=Path)
    parser.add_argument(
        "--mode",
        choices=("rules", "rules+llm", "rules+score", "full"),
        default="rules",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--revisions", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--log-file", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if args.log_file:
        handlers.append(logging.FileHandler(args.log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )

    cases = load_cases(args.directory)
    if args.limit > 0:
        cases = cases[: args.limit]

    verifier = LLMVerifier() if args.mode in ("rules+llm", "full") else None
    scorer = LLMScorer() if args.mode in ("rules+score", "full") else None
    adapter = QualityAdapter(verifier=verifier, scorer=scorer)
    revise = LLMReviser().revise if args.revisions else None
    loop = QualityLoop() if args.revisions else None

    results = run_calibration(
        cases,
        make_review(adapter, args.mode),
        revise=revise,
        loop=loop,
    )
    summary = summarize(results)
    payload = {
        "mode": args.mode,
        "revisions": args.revisions,
        "summary": summary,
        "results": [row.to_dict() for row in results],
    }

    if args.output:
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
