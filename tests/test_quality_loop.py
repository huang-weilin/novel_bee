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
    *,
    score: int | None = None,
    findings: list[RuleFinding] | None = None,
) -> QualityReport:
    return QualityReport(
        passed=decision is Decision.ACCEPT,
        decision=decision,
        score=score,
        failures=list(findings or []),
    )


def sequence_review(reports):
    remaining = list(reports)
    calls = []

    def review(chapter):
        calls.append(chapter)
        return remaining.pop(0)

    return review, calls


def recording_revise():
    requests = []

    def revise(chapter, request):
        requests.append(request)
        return ChapterInput(
            content=f"revised-{request.attempt}",
            project_id=chapter.project_id,
            chapter_seq=chapter.chapter_seq,
        )

    return revise, requests


def test_accept_on_first_attempt() -> None:
    review, calls = sequence_review([report(Decision.ACCEPT, score=80)])
    revise, requests = recording_revise()

    result = QualityLoop().run(ChapterInput(content="original"), review, revise)

    assert result.stopped_reason == "accept"
    assert result.report.decision is Decision.ACCEPT
    assert result.rewrite_count == 0
    assert result.polish_count == 0
    assert len(calls) == 1
    assert requests == []


def test_polish_then_accept() -> None:
    review, calls = sequence_review(
        [report(Decision.POLISH, score=60), report(Decision.ACCEPT, score=80)]
    )
    revise, requests = recording_revise()

    result = QualityLoop().run(ChapterInput(content="original"), review, revise)

    assert result.stopped_reason == "accept"
    assert result.polish_count == 1
    assert result.rewrite_count == 0
    assert len(calls) == 2
    assert requests[0].action is Decision.POLISH
    assert requests[0].attempt == 1
    assert result.attempts[0].action == "polish"


def test_rewrite_then_accept() -> None:
    review, _ = sequence_review(
        [report(Decision.REWRITE, score=40), report(Decision.ACCEPT, score=78)]
    )
    revise, requests = recording_revise()

    result = QualityLoop().run(ChapterInput(content="original"), review, revise)

    assert result.stopped_reason == "accept"
    assert result.rewrite_count == 1
    assert requests[0].action is Decision.REWRITE


def test_rewrite_limit_goes_human_review() -> None:
    review, calls = sequence_review([report(Decision.REWRITE, score=40)] * 10)
    revise, requests = recording_revise()

    result = QualityLoop(max_rewrites=3).run(
        ChapterInput(content="original"), review, revise
    )

    assert result.stopped_reason == "rewrite_limit"
    assert result.report.decision is Decision.HUMAN_REVIEW
    assert result.rewrite_count == 3
    assert len(requests) == 3
    assert len(calls) == 4
    assert result.attempts[-1].action == "rewrite_limit"


def test_polish_limit_goes_human_review() -> None:
    review, calls = sequence_review([report(Decision.POLISH, score=60)] * 10)
    revise, requests = recording_revise()

    result = QualityLoop(max_polish=2).run(
        ChapterInput(content="original"), review, revise
    )

    assert result.stopped_reason == "polish_limit"
    assert result.report.decision is Decision.HUMAN_REVIEW
    assert result.polish_count == 2
    assert len(requests) == 2
    assert len(calls) == 3


def test_initial_human_review_stops_immediately() -> None:
    review, calls = sequence_review([report(Decision.HUMAN_REVIEW)])
    revise, requests = recording_revise()

    result = QualityLoop().run(ChapterInput(content="original"), review, revise)

    assert result.stopped_reason == "human_review"
    assert result.report.decision is Decision.HUMAN_REVIEW
    assert len(calls) == 1
    assert requests == []


def test_revision_error_goes_human_review() -> None:
    review, _ = sequence_review([report(Decision.REWRITE, score=30)])

    def revise(chapter, request):
        raise RuntimeError("model unavailable")

    result = QualityLoop().run(ChapterInput(content="original"), review, revise)

    assert result.stopped_reason.startswith("revision_error")
    assert result.report.decision is Decision.HUMAN_REVIEW
    assert any("model unavailable" in note for note in result.report.notes)


def test_revision_request_carries_failures() -> None:
    finding = RuleFinding("Q07", Severity.BLOCKER, "说明书式对话", "改成动作")
    review, _ = sequence_review(
        [
            report(Decision.REWRITE, score=40, findings=[finding]),
            report(Decision.ACCEPT, score=80),
        ]
    )
    revise, requests = recording_revise()

    QualityLoop().run(ChapterInput(content="original"), review, revise)

    request = requests[0]
    assert request.failures[0].rule_id == "Q07"
    assert request.reason == "blocker: Q07"
    assert request.to_dict()["failures"][0]["evidence"] == "说明书式对话"


def test_result_serialization() -> None:
    review, _ = sequence_review([report(Decision.ACCEPT, score=80)])
    revise, _ = recording_revise()

    result = QualityLoop().run(ChapterInput(content="original"), review, revise)
    payload = result.to_dict()

    assert payload["stopped_reason"] == "accept"
    assert payload["report"]["score"] == 80
    assert payload["attempts"][0]["decision"] == "accept"
