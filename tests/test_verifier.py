import json

import pytest

from novel_pipeline.quality.models import ChapterInput, Severity
from novel_pipeline.quality.verifier import (
    LLMVerifier,
    VerifierError,
    build_prompt,
    parse_output,
)


def test_parse_valid_output() -> None:
    raw = json.dumps(
        {
            "findings": [
                {"rule_id": "Q07", "hit": True, "evidence": "甲", "suggestion": "乙"},
                {"rule_id": "Q08", "hit": True, "evidence": "丙", "suggestion": "丁"},
            ]
        },
        ensure_ascii=False,
    )
    findings = parse_output(raw)
    assert [finding.rule_id for finding in findings] == ["Q07", "Q08"]
    assert findings[0].severity is Severity.BLOCKER
    assert findings[1].severity is Severity.MAJOR


def test_parse_code_fence_and_empty_findings() -> None:
    assert parse_output('```json\n{"findings": []}\n```') == []


def test_parse_skips_hit_false_and_unknown_rule() -> None:
    raw = json.dumps(
        {
            "findings": [
                {"rule_id": "Q07", "hit": False, "evidence": "甲"},
                {"rule_id": "Q09", "hit": True, "evidence": "乙"},
            ]
        },
        ensure_ascii=False,
    )
    assert parse_output(raw) == []


def test_parse_rejects_missing_hit() -> None:
    with pytest.raises(VerifierError):
        parse_output('{"findings": [{"rule_id": "Q07", "evidence": "甲"}]}')


def test_parse_truncates_evidence() -> None:
    raw = json.dumps(
        {"findings": [{"rule_id": "Q07", "hit": True, "evidence": "甲" * 200}]},
        ensure_ascii=False,
    )
    assert len(parse_output(raw)[0].evidence) == 80


def test_verifier_retries_then_succeeds() -> None:
    calls: list[str] = []
    responses = iter(["not json", json.dumps({"findings": []})])

    def fake(prompt: str) -> str:
        calls.append(prompt)
        return next(responses)

    result = LLMVerifier(complete=fake).verify(
        ChapterInput(content="正文", outline="大纲", character_brief="角色")
    )
    assert result.human_review is False
    assert result.findings == []
    assert len(calls) == 2


def test_verifier_human_review_after_retry() -> None:
    calls: list[str] = []

    def fake(prompt: str) -> str:
        calls.append(prompt)
        return "not json"

    result = LLMVerifier(complete=fake).verify(ChapterInput(content="正文"))
    assert result.human_review is True
    assert result.error
    assert len(calls) == 2


def test_verifier_empty_content_skips_call() -> None:
    calls: list[str] = []

    def fake(prompt: str) -> str:
        calls.append(prompt)
        return '{"findings": []}'

    result = LLMVerifier(complete=fake).verify(ChapterInput(content="   "))
    assert result.human_review is True
    assert calls == []


def test_prompt_contains_context() -> None:
    prompt = build_prompt(
        ChapterInput(content="正文内容", outline="大纲内容", character_brief="角色内容")
    )
    assert "大纲内容" in prompt
    assert "角色内容" in prompt
    assert "正文内容" in prompt
