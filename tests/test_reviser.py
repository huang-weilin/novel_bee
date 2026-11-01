import pytest

from novel_pipeline.quality.loop import RevisionRequest
from novel_pipeline.quality.models import (
    ChapterInput,
    Decision,
    RuleFinding,
    Severity,
)
from novel_pipeline.quality.reviser import (
    LLMReviser,
    RevisionError,
    build_revision_prompt,
    clean_output,
)


def request(action: Decision = Decision.REWRITE) -> RevisionRequest:
    return RevisionRequest(
        action=action,
        attempt=1,
        failures=(
            RuleFinding(
                "Q01",
                Severity.MAJOR,
                "连续单句段 3 段",
                "合并相邻单句段",
            ),
        ),
        score=60,
        dimensions={"character": 60},
        reason="score: 60",
    )


def test_build_prompt_contains_failure_and_content() -> None:
    prompt = build_revision_prompt(ChapterInput(content="原正文"), request())
    assert "连续单句段 3 段" in prompt
    assert "合并相邻单句段" in prompt
    assert "原正文" in prompt
    assert "重写" in prompt


def test_polish_prompt_uses_polish_mode() -> None:
    prompt = build_revision_prompt(
        ChapterInput(content="原正文"), request(Decision.POLISH)
    )
    assert "局部打磨" in prompt


def test_clean_output_strips_code_fence_and_label() -> None:
    assert clean_output("```\n修订后的正文：新正文\n```") == "新正文"


def test_empty_output_is_rejected() -> None:
    with pytest.raises(RevisionError):
        clean_output("   ")


def test_reviser_returns_new_chapter() -> None:
    reviser = LLMReviser(complete=lambda prompt: "这是修订后的正文。")
    chapter = ChapterInput(content="原正文", project_id="p1", chapter_seq=1)
    revised = reviser.revise(chapter, request())
    assert revised.content == "这是修订后的正文。"
    assert revised.project_id == "p1"
    assert revised.chapter_seq == 1
