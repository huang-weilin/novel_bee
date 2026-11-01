import json

import pytest

from novel_pipeline.quality.calibrate import (
    CalibrationCase,
    CalibrationResult,
    load_cases,
    run_calibration,
    summarize,
)
from novel_pipeline.quality.loop import QualityLoop
from novel_pipeline.quality.models import (
    ChapterInput,
    Decision,
    QualityReport,
    RuleFinding,
    Severity,
)


def report(
    decision: Decision,
    score: int | None = None,
    findings: list[RuleFinding] | None = None,
) -> QualityReport:
    return QualityReport(
        passed=decision is Decision.ACCEPT,
        decision=decision,
        score=score,
        failures=list(findings or []),
    )


def test_load_cases_with_sidecar(tmp_path) -> None:
    (tmp_path / "ch01.md").write_text("正文一", encoding="utf-8")
    (tmp_path / "ch01.json").write_text(
        json.dumps(
            {
                "project_id": "p1",
                "chapter_seq": 1,
                "genre": "仙侠",
                "outline": "大纲",
                "character_brief": "角色",
                "style_constraints": "冷峻",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "ch02.txt").write_text("正文二", encoding="utf-8")

    cases = load_cases(tmp_path)

    assert [case.name for case in cases] == ["ch01", "ch02"]
    assert cases[0].chapter.project_id == "p1"
    assert cases[0].chapter.genre == "仙侠"
    assert cases[1].chapter.project_id == "ch02"


def test_load_cases_requires_files(tmp_path) -> None:
    with pytest.raises(ValueError):
        load_cases(tmp_path)


def test_run_calibration_without_revisions() -> None:
    cases = [
        CalibrationCase("a", ChapterInput(content="一")),
        CalibrationCase("b", ChapterInput(content="二")),
    ]
    decisions = iter(
        [report(Decision.ACCEPT, 80), report(Decision.REWRITE, 40)]
    )

    def review(chapter):
        return next(decisions)

    results = run_calibration(cases, review)

    assert [row.decision for row in results] == ["accept", "rewrite"]
    assert results[0].stopped_reason == "review_only"
    assert results[1].score == 40
    assert results[1].initial_decision == "rewrite"
    assert results[1].initial_score == 40


def test_run_calibration_with_loop() -> None:
    cases = [CalibrationCase("a", ChapterInput(content="一"))]
    reports = iter(
        [
            report(
                Decision.POLISH,
                60,
                [RuleFinding("Q01", Severity.MAJOR, "单句段")],
            ),
            report(Decision.ACCEPT, 80),
        ]
    )

    def review(chapter):
        return next(reports)

    def revise(chapter, request):
        return ChapterInput(content=f"revised-{request.attempt}")

    results = run_calibration(
        cases,
        review,
        revise=revise,
        loop=QualityLoop(),
    )

    assert len(results) == 1
    assert results[0].decision == "accept"
    assert results[0].initial_decision == "polish"
    assert results[0].initial_score == 60
    assert results[0].initial_rule_ids == ["Q01"]
    assert results[0].polish_count == 1
    assert results[0].attempts == 2
    assert results[0].stopped_reason == "accept"


def test_run_calibration_records_errors() -> None:
    cases = [CalibrationCase("bad", ChapterInput(content="一"))]

    def review(chapter):
        raise RuntimeError("boom")

    results = run_calibration(cases, review)

    assert results[0].decision == "error"
    assert results[0].error == "boom"


def test_summarize() -> None:
    results = [
        CalibrationResult("a", "accept", 85, ["Q05"]),
        CalibrationResult("b", "polish", 65, ["Q01", "Q01"]),
        CalibrationResult("c", "rewrite", 40, ["Q07"], rewrite_count=1),
    ]
    summary = summarize(results)

    assert summary["chapters"] == 3
    assert summary["decisions"] == {"accept": 1, "polish": 1, "rewrite": 1}
    assert summary["initial_decisions"] == {
        "accept": 1,
        "polish": 1,
        "rewrite": 1,
    }
    assert summary["avg_initial_score"] == 63.33
    assert summary["avg_score"] == 63.33
    assert summary["score_buckets"] == {
        "0-39": 0,
        "40-54": 1,
        "55-74": 1,
        "75-100": 1,
    }
    assert summary["rule_hits"]["Q01"] == 2
    assert summary["avg_rewrites"] == 0.33
    assert summary["max_rewrites"] == 1
