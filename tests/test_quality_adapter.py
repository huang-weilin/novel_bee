import json
import logging

from novel_pipeline.quality.adapter import QualityAdapter
from novel_pipeline.quality.models import (
    ChapterInput,
    Decision,
    RuleFinding,
    Severity,
)
from novel_pipeline.quality.scorer import ScoreResult
from novel_pipeline.quality.verifier import VerifierResult


class FakeEngine:
    def __init__(self, findings):
        self.findings = findings

    def check(
        self,
        text: str,
        *,
        genre: str = "",
        target_words: int | None = None,
    ):
        return list(self.findings)


class FakeVerifier:
    def __init__(self, result):
        self.result = result

    def verify(self, chapter):
        return self.result


class FakeScorer:
    def __init__(self, result):
        self.result = result

    def score(self, chapter):
        return self.result


def score_result(value: int) -> ScoreResult:
    return ScoreResult(
        dimensions={
            "character": value,
            "pacing": value,
            "hook": value,
            "style": value,
        },
        score=value,
        reasons={"character": "理由"},
    )


class ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record.getMessage())


def make_adapter(findings, verifier=None, scorer=None):
    logger = logging.getLogger("test-quality-adapter")
    handler = ListHandler()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return (
        QualityAdapter(
            engine=FakeEngine(findings),
            verifier=verifier,
            scorer=scorer,
            log=logger,
        ),
        handler,
    )


def test_log_only_passes_through() -> None:
    adapter, handler = make_adapter([])
    report = adapter.review(
        ChapterInput(content="正文", project_id="p1", chapter_seq=1),
        mode="log_only",
    )
    assert report.passed is True
    assert report.decision is Decision.ACCEPT
    assert report.failures == []
    assert report.notes == ["log_only"]
    assert "quality_review" in handler.records[0]
    assert "sha256_12" in handler.records[0]


def test_rules_mode_polishes_on_major() -> None:
    adapter, _ = make_adapter(
        [RuleFinding("Q01", Severity.MAJOR, "单句段过多")]
    )
    report = adapter.review(ChapterInput(content="正文"), mode="rules")
    assert report.passed is False
    assert report.decision is Decision.POLISH
    assert len(report.failures) == 1


def test_rules_mode_accepts_with_only_minor() -> None:
    adapter, _ = make_adapter(
        [RuleFinding("Q06", Severity.MINOR, "四字片段重复")]
    )
    report = adapter.review(ChapterInput(content="正文"), mode="rules")
    assert report.passed is True
    assert report.decision is Decision.ACCEPT


def test_rules_mode_rewrites_on_blocker() -> None:
    adapter, _ = make_adapter(
        [RuleFinding("Q07", Severity.BLOCKER, "角色说明书式表达")]
    )
    report = adapter.review(ChapterInput(content="正文"), mode="rules")
    assert report.passed is False
    assert report.decision is Decision.REWRITE


def test_rules_llm_rewrites_on_verifier_blocker() -> None:
    verifier = FakeVerifier(
        VerifierResult(
            findings=[RuleFinding("Q07", Severity.BLOCKER, "说明书式对话")]
        )
    )
    adapter, _ = make_adapter([], verifier=verifier)
    report = adapter.review(ChapterInput(content="正文"), mode="rules+llm")
    assert report.passed is False
    assert report.decision is Decision.REWRITE
    assert [finding.rule_id for finding in report.failures] == ["Q07"]


def test_rules_llm_goes_human_review_on_verifier_failure() -> None:
    verifier = FakeVerifier(
        VerifierResult(error="bad json", human_review=True)
    )
    adapter, _ = make_adapter([], verifier=verifier)
    report = adapter.review(ChapterInput(content="正文"), mode="rules+llm")
    assert report.passed is False
    assert report.decision is Decision.HUMAN_REVIEW
    assert any("verifier_error" in note for note in report.notes)


def test_rules_llm_requires_verifier() -> None:
    adapter, _ = make_adapter([])
    try:
        adapter.review(ChapterInput(content="正文"), mode="rules+llm")
    except ValueError as exc:
        assert "requires a verifier" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_full_accepts_high_score() -> None:
    adapter, _ = make_adapter(
        [],
        verifier=FakeVerifier(VerifierResult()),
        scorer=FakeScorer(score_result(82)),
    )
    report = adapter.review(ChapterInput(content="正文"), mode="full")
    assert report.passed is True
    assert report.decision is Decision.ACCEPT
    assert report.score == 82
    assert report.dimensions["character"] == 82
    assert report.reasons["character"] == "理由"


def test_full_polishes_high_score_with_major() -> None:
    adapter, _ = make_adapter(
        [RuleFinding("Q01", Severity.MAJOR, "单句段过多")],
        verifier=FakeVerifier(VerifierResult()),
        scorer=FakeScorer(score_result(85)),
    )
    report = adapter.review(ChapterInput(content="正文"), mode="full")
    assert report.passed is False
    assert report.decision is Decision.POLISH


def test_full_polishes_mid_score() -> None:
    adapter, _ = make_adapter(
        [],
        verifier=FakeVerifier(VerifierResult()),
        scorer=FakeScorer(score_result(60)),
    )
    report = adapter.review(ChapterInput(content="正文"), mode="full")
    assert report.passed is False
    assert report.decision is Decision.POLISH


def test_full_rewrites_low_score() -> None:
    adapter, _ = make_adapter(
        [],
        verifier=FakeVerifier(VerifierResult()),
        scorer=FakeScorer(score_result(50)),
    )
    report = adapter.review(ChapterInput(content="正文"), mode="full")
    assert report.decision is Decision.REWRITE


def test_full_blocker_overrides_high_score() -> None:
    verifier = FakeVerifier(
        VerifierResult(findings=[RuleFinding("Q07", Severity.BLOCKER, "说明书")])
    )
    adapter, _ = make_adapter(
        [],
        verifier=verifier,
        scorer=FakeScorer(score_result(90)),
    )
    report = adapter.review(ChapterInput(content="正文"), mode="full")
    assert report.decision is Decision.REWRITE


def test_full_goes_human_review_on_scorer_failure() -> None:
    adapter, _ = make_adapter(
        [],
        verifier=FakeVerifier(VerifierResult()),
        scorer=FakeScorer(ScoreResult(error="bad score", human_review=True)),
    )
    report = adapter.review(ChapterInput(content="正文"), mode="full")
    assert report.passed is False
    assert report.decision is Decision.HUMAN_REVIEW
    assert any("scorer_error" in note for note in report.notes)


def test_rules_score_uses_score_without_verifier() -> None:
    adapter, _ = make_adapter([], scorer=FakeScorer(score_result(60)))
    report = adapter.review(ChapterInput(content="正文"), mode="rules+score")
    assert report.decision is Decision.POLISH
    assert report.score == 60


def test_rules_score_requires_scorer() -> None:
    adapter, _ = make_adapter([])
    try:
        adapter.review(ChapterInput(content="正文"), mode="rules+score")
    except ValueError as exc:
        assert "requires a scorer" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_full_requires_scorer() -> None:
    adapter, _ = make_adapter([], verifier=FakeVerifier(VerifierResult()))
    try:
        adapter.review(ChapterInput(content="正文"), mode="full")
    except ValueError as exc:
        assert "requires a scorer" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_mapping_input_and_serialization() -> None:
    adapter, _ = make_adapter([])
    report = adapter.review(
        {
            "content": "正文",
            "project_id": "p1",
            "chapter_seq": 2,
            "target_words": 1800,
        },
        mode="rules",
    )
    payload = report.to_dict()
    assert payload["decision"] == "accept"
    assert json.dumps(payload, ensure_ascii=False)
