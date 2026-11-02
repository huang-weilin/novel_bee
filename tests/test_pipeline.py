import json

import pytest

from novel_pipeline.memory import (
    ConsistencyEngine,
    ConsistencyReport,
    MemoryExtractor,
    MemoryStore,
)
from novel_pipeline.pipeline import (
    ChapterPipeline,
    GenerationRequest,
    LLMChapterReviser,
    run_chapter,
)
from novel_pipeline.planning import ScenePlan
from novel_pipeline.quality.models import (
    ChapterInput,
    Decision,
    QualityReport,
    RuleFinding,
    Severity,
)


def extraction_json(**overrides) -> str:
    data = {
        "character_updates": [],
        "item_usage": [],
        "info_gains": [],
        "foreshadowing": [],
        "chapter_summary": "本章摘要",
        "key_events": [],
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


def seed_project() -> tuple[MemoryStore, str]:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    return store, project.id


class FixedQuality:
    def __init__(
        self,
        decision: Decision = Decision.ACCEPT,
        findings: list[RuleFinding] | None = None,
        score: int | None = 80,
    ) -> None:
        self.decision = decision
        self.findings = list(findings or [])
        self.score = score
        self.calls: list[ChapterInput] = []

    def review(
        self, chapter: ChapterInput, *, mode: str = "rules"
    ) -> QualityReport:
        self.calls.append(chapter)
        return QualityReport(
            passed=self.decision is Decision.ACCEPT,
            decision=self.decision,
            failures=list(self.findings),
            score=self.score,
            notes=["fixed-quality"],
        )


class SequenceQuality:
    def __init__(self, *reports: QualityReport) -> None:
        self.reports = list(reports)
        self.calls: list[ChapterInput] = []

    def review(
        self, chapter: ChapterInput, *, mode: str = "rules"
    ) -> QualityReport:
        self.calls.append(chapter)
        return self.reports.pop(0)


class ScriptedWriter:
    def __init__(self, *drafts: str) -> None:
        self.drafts = list(drafts)
        self.contexts = []
        self.requests = []

    def write(self, context, request):
        self.contexts.append(context)
        self.requests.append(request)
        return self.drafts.pop(0)


class ScriptedReviser:
    def __init__(self, *drafts: str) -> None:
        self.drafts = list(drafts)
        self.requests = []
        self.contexts = []

    def revise(self, chapter, request, context):
        self.requests.append(request)
        self.contexts.append(context)
        return self.drafts.pop(0)


def make_request(
    project_id: str,
    seq: int = 1,
    *,
    scene_plan: ScenePlan | None = None,
) -> GenerationRequest:
    return GenerationRequest(
        project_id=project_id,
        chapter_seq=seq,
        outline="李四进屋探查",
        scene_plan=scene_plan,
        target_words=1500,
    )


def test_happy_path_finalizes_and_applies_summary() -> None:
    store, project_id = seed_project()
    writer = ScriptedWriter("李四走进房间，关上门。")
    extractor = MemoryExtractor(
        complete=lambda prompt: extraction_json(
            chapter_summary="李四进屋探查。"
        )
    )
    pipeline = ChapterPipeline(
        store,
        writer=writer,
        quality=FixedQuality(),
        extractor=extractor,
    )

    result = pipeline.run(make_request(project_id))

    assert result.status == "final"
    assert result.error is None
    assert result.context_tokens > 0
    assert "李四进屋探查" in writer.contexts[0].text
    assert result.attempts[-1].action == "accept"
    assert result.applied is not None
    assert result.applied.needs_review == []
    saved = store.get_chapter(project_id, 1)
    assert saved is not None
    assert saved.status == "final"
    assert saved.content == "李四走进房间，关上门。"
    assert saved.summary == "李四进屋探查。"
    assert result.to_dict()["status"] == "final"


def test_quality_input_carries_generation_target_words() -> None:
    store, project_id = seed_project()
    quality = FixedQuality()
    pipeline = ChapterPipeline(
        store,
        writer=ScriptedWriter("李四走进房间，关上门。"),
        quality=quality,
        extractor=MemoryExtractor(
            complete=lambda prompt: extraction_json(
                chapter_summary="李四进屋探查。"
            )
        ),
    )

    pipeline.run(make_request(project_id))

    assert quality.calls[0].target_words == 1500


def test_r01_blocker_triggers_rewrite_then_finalizes() -> None:
    store, project_id = seed_project()
    store.upsert_character(project_id, "张三", alive=False, status="已死亡")
    writer = ScriptedWriter("张三说：我回来了。")
    reviser = ScriptedReviser("李四走进房间，关上门。")
    extractor = MemoryExtractor(
        complete=lambda prompt: extraction_json(
            chapter_summary="李四进屋。"
        )
    )
    pipeline = ChapterPipeline(
        store,
        writer=writer,
        reviser=reviser,
        quality=FixedQuality(),
        extractor=extractor,
    )

    result = pipeline.run(make_request(project_id))

    assert result.status == "final"
    assert [attempt.action for attempt in result.attempts] == [
        "rewrite",
        "accept",
    ]
    assert result.attempts[0].rule_ids == ("R01",)
    assert len(reviser.requests) == 1
    assert reviser.requests[0].failures[0].rule_id == "R01"
    assert "张三" in reviser.requests[0].failures[0].evidence
    saved = store.get_chapter(project_id, 1)
    assert saved is not None
    assert saved.status == "final"
    assert saved.content == "李四走进房间，关上门。"
    assert saved.rewrite_count == 1


def test_extraction_failure_stays_pending_without_applying() -> None:
    store, project_id = seed_project()
    extractor = MemoryExtractor(
        complete=lambda prompt: "not json", retries=0
    )
    pipeline = ChapterPipeline(
        store,
        writer=ScriptedWriter("李四走进房间。"),
        quality=FixedQuality(),
        extractor=extractor,
    )

    result = pipeline.run(make_request(project_id))

    assert result.status == "pending"
    assert result.extraction is not None
    assert result.extraction.human_review is True
    assert result.applied is None
    assert result.quality is not None
    assert result.quality.decision is Decision.HUMAN_REVIEW
    saved = store.get_chapter(project_id, 1)
    assert saved is not None
    assert saved.status == "pending"
    assert saved.summary is None


def test_unknown_extraction_entity_stays_pending() -> None:
    store, project_id = seed_project()
    extractor = MemoryExtractor(
        complete=lambda prompt: extraction_json(
            character_updates=[
                {"name": "王五", "status": "新角色", "confidence": 0.9}
            ]
        )
    )
    pipeline = ChapterPipeline(
        store,
        writer=ScriptedWriter("王五走进房间。"),
        quality=FixedQuality(),
        extractor=extractor,
    )

    result = pipeline.run(make_request(project_id))

    assert result.status == "pending"
    assert result.applied is not None
    assert [item.reason for item in result.applied.needs_review] == [
        "unknown_character"
    ]
    saved = store.get_chapter(project_id, 1)
    assert saved is not None
    assert saved.status == "pending"
    assert saved.summary is None
    assert store.get_character(project_id, "王五") is None


def test_major_consistency_finding_goes_human_review_without_revision() -> None:
    store, project_id = seed_project()
    store.create_foreshadowing(
        project_id, "青铜钥匙", 1, target_chapter=1
    )
    reviser = ScriptedReviser("不该被调用。")
    pipeline = ChapterPipeline(
        store,
        writer=ScriptedWriter("李四走进房间。"),
        reviser=reviser,
        quality=FixedQuality(),
        extractor=MemoryExtractor(
            complete=lambda prompt: extraction_json()
        ),
    )

    result = pipeline.run(make_request(project_id, 2))

    assert result.status == "pending"
    assert result.consistency is not None
    assert result.consistency.findings[0].rule_id == "R06"
    assert result.quality is not None
    assert result.quality.decision is Decision.HUMAN_REVIEW
    assert reviser.requests == []
    assert store.get_chapter(project_id, 2).status == "pending"  # type: ignore[union-attr]


def test_minor_consistency_finding_does_not_force_human_review() -> None:
    quality = QualityReport(
        passed=True, decision=Decision.ACCEPT, score=80
    )
    consistency = ConsistencyReport(
        findings=[
            RuleFinding(
                rule_id="R07",
                severity=Severity.MINOR,
                evidence="情感债「解释」已到期",
                suggestion="可以故意拖",
            )
        ]
    )

    combined = ChapterPipeline._combine_reports(quality, consistency)

    assert combined.decision is Decision.ACCEPT
    assert combined.passed is True
    assert [finding.rule_id for finding in combined.failures] == ["R07"]


def test_extractor_and_consistency_confidence_must_match() -> None:
    store, _ = seed_project()
    extractor = MemoryExtractor(min_confidence=0.8)
    consistency = ConsistencyEngine(store, min_confidence=0.7)

    with pytest.raises(ValueError, match="min_confidence"):
        ChapterPipeline(
            store,
            extractor=extractor,
            consistency=consistency,
        )


def test_pipeline_passes_scene_plan_to_writer() -> None:
    store, project_id = seed_project()
    writer = ScriptedWriter("李四走进房间。")
    pipeline = ChapterPipeline(
        store,
        writer=writer,
        quality=FixedQuality(),
        extractor=MemoryExtractor(
            complete=lambda prompt: extraction_json()
        ),
    )
    plan = ScenePlan(
        goal="让李四说出密道入口",
        obstacle="李四怕隔墙有耳",
        emotional_target="怀疑→暂时合作",
        release="李四把灯芯压低，说了半句",
        reader_promise="读者想看张三用一句旧案把李四逼到开口",
        payoff="李四说出密道入口，张三当场记下",
        payoff_type="识破",
    )

    result = pipeline.run(make_request(project_id, scene_plan=plan))

    assert result.status == "final"
    assert "让李四说出密道入口" in writer.contexts[0].text
    assert "怀疑→暂时合作" in writer.contexts[0].text
    assert "读者想看张三用一句旧案把李四逼到开口" in writer.contexts[0].text
    assert "李四说出密道入口" in writer.contexts[0].text


def test_reviser_prompt_repairs_connections_before_cutting() -> None:
    assert "先补承接" in LLMChapterReviser.SYSTEM
    assert "把所有句子改短" in LLMChapterReviser.SYSTEM
    assert "不要把叙述段落切成动作提示" in LLMChapterReviser.SYSTEM


def test_run_chapter_wrapper() -> None:
    store, project_id = seed_project()
    result = run_chapter(
        store,
        make_request(project_id),
        writer=ScriptedWriter("李四走进房间。"),
        quality=FixedQuality(),
        extractor=MemoryExtractor(
            complete=lambda prompt: extraction_json()
        ),
    )

    assert result.status == "final"
    assert store.get_chapter(project_id, 1).status == "final"  # type: ignore[union-attr]


def test_character_brief_and_fenced_title_are_handled() -> None:
    store, project_id = seed_project()
    store.upsert_character(project_id, "李四", status="巡夜人")
    quality = FixedQuality()
    pipeline = ChapterPipeline(
        store,
        writer=ScriptedWriter(
            "```markdown\n# 第一章 夜行\n李四走进房间。\n```"
        ),
        quality=quality,
        extractor=MemoryExtractor(
            complete=lambda prompt: extraction_json()
        ),
    )

    result = pipeline.run(make_request(project_id))

    assert result.status == "final"
    assert quality.calls[0].character_brief == "李四：巡夜人"
    assert result.chapter is not None
    assert result.chapter.content == "李四走进房间。"


def test_quality_rewrite_finding_is_sent_to_reviser() -> None:
    store, project_id = seed_project()
    finding = RuleFinding(
        "Q01", Severity.BLOCKER, "总结式收尾", "改成场景收束"
    )
    quality = SequenceQuality(
        QualityReport(
            passed=False,
            decision=Decision.REWRITE,
            failures=[finding],
            score=40,
        ),
        QualityReport(passed=True, decision=Decision.ACCEPT, score=80),
    )
    reviser = ScriptedReviser("李四走进房间。")
    extractor_calls: list[str] = []
    pipeline = ChapterPipeline(
        store,
        writer=ScriptedWriter("总之，故事结束了。"),
        reviser=reviser,
        quality=quality,
        extractor=MemoryExtractor(
            complete=lambda prompt: (
                extractor_calls.append(prompt) or extraction_json()
            )
        ),
    )

    result = pipeline.run(make_request(project_id))

    assert result.status == "final"
    assert reviser.requests[0].failures[0].rule_id == "Q01"
    assert result.attempts[0].rule_ids == ("Q01",)
    # The rejected draft must not spend extractor tokens.
    assert len(extractor_calls) == 1
