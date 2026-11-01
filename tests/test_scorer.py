import json

import pytest

from novel_pipeline.quality.models import ChapterInput
from novel_pipeline.quality.scorer import (
    LLMScorer,
    build_prompt,
    parse_output,
)
from novel_pipeline.quality.verifier import VerifierError

VALID = {
    "dimensions": {"character": 72, "pacing": 65, "hook": 70, "style": 64},
    "reasons": {
        "character": "行为与档案一致",
        "pacing": "中段略慢",
        "hook": "章末有悬念",
        "style": "语言干净",
    },
}


def test_parse_valid_output() -> None:
    result = parse_output(json.dumps(VALID, ensure_ascii=False))
    assert result.dimensions == VALID["dimensions"]
    assert result.score == 68
    assert result.reasons["character"] == "行为与档案一致"


def test_parse_code_fence() -> None:
    raw = "```json\n" + json.dumps(VALID) + "\n```"
    assert parse_output(raw).score == 68


def test_parse_rejects_missing_dimension() -> None:
    payload = {"dimensions": {"character": 70, "pacing": 70, "hook": 70}}
    with pytest.raises(VerifierError):
        parse_output(json.dumps(payload))


def test_parse_rejects_out_of_range() -> None:
    payload = {
        "dimensions": {"character": 101, "pacing": 70, "hook": 70, "style": 70}
    }
    with pytest.raises(VerifierError):
        parse_output(json.dumps(payload))


def test_parse_rejects_boolean_dimension() -> None:
    payload = {
        "dimensions": {"character": True, "pacing": 70, "hook": 70, "style": 70}
    }
    with pytest.raises(VerifierError):
        parse_output(json.dumps(payload))


def test_scorer_retries_then_succeeds() -> None:
    calls: list[str] = []
    responses = iter(["not json", json.dumps(VALID)])

    def fake(prompt: str) -> str:
        calls.append(prompt)
        return next(responses)

    result = LLMScorer(complete=fake).score(ChapterInput(content="正文"))
    assert result.human_review is False
    assert result.score == 68
    assert len(calls) == 2


def test_scorer_human_review_after_retry() -> None:
    calls: list[str] = []

    def fake(prompt: str) -> str:
        calls.append(prompt)
        return "not json"

    result = LLMScorer(complete=fake).score(ChapterInput(content="正文"))
    assert result.human_review is True
    assert result.error
    assert len(calls) == 2


def test_scorer_empty_content_skips_call() -> None:
    calls: list[str] = []

    def fake(prompt: str) -> str:
        calls.append(prompt)
        return json.dumps(VALID)

    result = LLMScorer(complete=fake).score(ChapterInput(content="  "))
    assert result.human_review is True
    assert calls == []


def test_prompt_contains_style_constraints() -> None:
    prompt = build_prompt(
        ChapterInput(
            content="正文内容",
            outline="大纲内容",
            character_brief="角色内容",
            style_constraints="冷峻克制",
        )
    )
    assert "大纲内容" in prompt
    assert "角色内容" in prompt
    assert "冷峻克制" in prompt
    assert "正文内容" in prompt
