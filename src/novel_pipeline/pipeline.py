"""End-to-end chapter pipeline.

The M2 quality layer and M3 memory layer were built as independent libraries.
This module wires them into one generation path:

    context -> draft -> quality + extraction + consistency -> revision loop
    -> finalize -> apply structured memory

The writer, reviser, and quality gate are injectable. Tests use fakes; the
default implementations use the configured LLM endpoint. A real generation
run must pass through this class, so the "定稿前拦住" promise is no longer
only a library-level capability.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from .config import LLMConfig
from .llm import LLMClient
from .memory import (
    ApplyResult,
    AssembledContext,
    ConsistencyEngine,
    ConsistencyReport,
    ContextAssembler,
    ContextBudget,
    ExtractionResult,
    MemoryContext,
    MemoryExtractor,
    MemoryStore,
)
from .memory.extractor import DEFAULT_MIN_CONFIDENCE
from .planning import ScenePlan
from .quality.adapter import QualityAdapter
from .quality.loop import LoopAttempt, QualityLoop, RevisionRequest
from .quality.models import (
    ChapterInput,
    Decision,
    QualityReport,
    Severity,
)

DEFAULT_WRITER_MAX_TOKENS = 16_384
DEFAULT_REVISER_MAX_TOKENS = 16_384


class ChapterWriter(Protocol):
    def write(
        self, context: AssembledContext, request: GenerationRequest
    ) -> str: ...


class ChapterReviser(Protocol):
    def revise(
        self,
        chapter: ChapterInput,
        request: RevisionRequest,
        context: AssembledContext,
    ) -> str: ...


@dataclass(frozen=True)
class GenerationRequest:
    project_id: str
    chapter_seq: int
    outline: str
    style_constraints: str = ""
    scene_plan: ScenePlan | None = None
    target_words: int = 2000
    pov: str = "第三人称"
    title: str | None = None
    character_brief: str = ""

    def __post_init__(self) -> None:
        if self.chapter_seq < 1:
            raise ValueError("chapter_seq must be positive")
        if self.target_words < 1:
            raise ValueError("target_words must be positive")


@dataclass
class PipelineResult:
    request: GenerationRequest
    chapter: ChapterInput | None = None
    status: str = "failed"  # final | pending | failed
    quality: QualityReport | None = None
    consistency: ConsistencyReport | None = None
    extraction: ExtractionResult | None = None
    applied: ApplyResult | None = None
    context_tokens: int = 0
    attempts: list[LoopAttempt] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "chapter": (
                {
                    "project_id": self.chapter.project_id,
                    "chapter_seq": self.chapter.chapter_seq,
                    "chars": len(self.chapter.content),
                    "content": self.chapter.content,
                }
                if self.chapter
                else None
            ),
            "quality": self.quality.to_dict() if self.quality else None,
            "consistency": (
                self.consistency.to_dict() if self.consistency else None
            ),
            "extraction": (
                self.extraction.to_dict() if self.extraction else None
            ),
            "applied": self.applied.to_dict() if self.applied else None,
            "context_tokens": self.context_tokens,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "notes": list(self.notes),
            "error": self.error,
        }


class LLMChapterWriter:
    """Default writer: send the assembled context to the configured model."""

    def __init__(
        self,
        client: LLMClient | None = None,
        *,
        max_tokens: int = DEFAULT_WRITER_MAX_TOKENS,
    ) -> None:
        self._client = client
        self.max_tokens = max_tokens

    def _get_client(self) -> LLMClient:
        if self._client is None:
            self._client = LLMClient(LLMConfig.from_env())
        return self._client

    def write(
        self, context: AssembledContext, request: GenerationRequest
    ) -> str:
        return self._get_client().complete(
            context.text,
            max_tokens=self.max_tokens,
        )


class LLMChapterReviser:
    """Default reviser: ask the model for a complete corrected chapter."""

    SYSTEM = """你是中文网络小说修订者。根据写作上下文和本章问题清单，输出完整修订后的本章正文。

修订顺序：先补承接（场景脊柱、因果桥、人物声口、关键物件回指），再删装饰。不要把“把所有句子改短”当成解决冗余的办法。

要求：
1. 只修改问题清单涉及的地方，保留原有情节、人物、场景和大致篇幅。
2. 不要把叙述段落切成动作提示；不要把每句对话拆成单独一段；保留必要的复合句、过渡句和人物内心判断。
3. 如果原文信息不足，先补一句动作、心理或环境承接，再删冗余；不要让读者靠猜来补时间、地点、因果。
4. 不同人物要有不同的句长、词汇、称呼和直接程度；不要把所有人物改成同一种短促语气。
5. 只输出正文，不要解释、标题、Markdown 或修改说明。"""

    def __init__(
        self,
        client: LLMClient | None = None,
        *,
        max_tokens: int = DEFAULT_REVISER_MAX_TOKENS,
    ) -> None:
        self._client = client
        self.max_tokens = max_tokens

    def _get_client(self) -> LLMClient:
        if self._client is None:
            self._client = LLMClient(LLMConfig.from_env())
        return self._client

    def revise(
        self,
        chapter: ChapterInput,
        request: RevisionRequest,
        context: AssembledContext,
    ) -> str:
        failures = "\n".join(
            f"- {item.rule_id} [{item.severity.value}]：{item.evidence}"
            + (f"；建议：{item.suggestion}" if item.suggestion else "")
            for item in request.failures
        )
        prompt = f"""【写作上下文】
{context.text}

【当前稿】
{chapter.content}

【需要修正的问题】
{failures or "（无具体条目，按质量评分与建议整体润色）"}

【修订原则】
先补承接，再删装饰；不要用更多形容词解决“画面感”问题，也不要把“把所有句子改短”当成修订。

请输出修订后的完整本章正文，只输出正文。"""
        return self._get_client().complete(
            prompt,
            system=self.SYSTEM,
            temperature=0.5,
            max_tokens=self.max_tokens,
        )


class ChapterPipeline:
    """Wire context, generation, quality, consistency, and extraction."""

    def __init__(
        self,
        store: MemoryStore,
        *,
        writer: ChapterWriter | None = None,
        reviser: ChapterReviser | None = None,
        extractor: MemoryExtractor | None = None,
        consistency: ConsistencyEngine | None = None,
        quality: QualityAdapter | None = None,
        assembler: ContextAssembler | None = None,
        quality_loop: QualityLoop | None = None,
        quality_mode: str = "rules",
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    ) -> None:
        self.store = store
        self.writer = writer or LLMChapterWriter()
        self.reviser = reviser
        self.min_confidence = min_confidence
        self.extractor = extractor or MemoryExtractor(
            min_confidence=min_confidence
        )
        self.consistency = consistency or ConsistencyEngine(
            store, min_confidence=min_confidence
        )
        left = getattr(self.extractor, "min_confidence", None)
        right = getattr(self.consistency, "min_confidence", None)
        if left is not None and right is not None and left != right:
            raise ValueError(
                "extractor and consistency min_confidence must match"
            )
        self.quality = quality or QualityAdapter()
        self.assembler = assembler or ContextAssembler(
            store, ContextBudget()
        )
        self.quality_loop = quality_loop or QualityLoop()
        self.quality_mode = quality_mode

    def run(self, request: GenerationRequest) -> PipelineResult:
        project = self.store.get_project(request.project_id)
        if project is None:
            raise KeyError(f"project not found: {request.project_id}")

        context = self.assembler.build(
            request.project_id,
            request.chapter_seq,
            outline=request.outline,
            style_constraints=request.style_constraints,
            scene_plan=request.scene_plan,
            target_words=request.target_words,
            pov=request.pov,
        )
        result = PipelineResult(
            request=request,
            context_tokens=context.token_estimate,
        )

        try:
            draft = _clean_draft(self.writer.write(context, request))
        except Exception as exc:  # noqa: BLE001 - writer failure is data
            result.error = f"writer_error: {exc}"
            return result
        if not draft:
            result.error = "writer returned an empty chapter"
            return result

        chapter = self._chapter_input(request, project.genre, draft)
        last_extraction: ExtractionResult | None = None
        last_consistency: ConsistencyReport | None = None

        def review(current: ChapterInput) -> QualityReport:
            nonlocal last_extraction, last_consistency
            quality_report = self.quality.review(
                current, mode=self.quality_mode
            )
            # A draft that already needs rewrite/polish does not get the
            # expensive extractor/consistency calls. They run on the draft
            # that quality has accepted, or on the final human-review draft.
            if quality_report.decision is not Decision.ACCEPT:
                return quality_report
            extraction = self.extractor.extract(
                current,
                MemoryContext.from_store(self.store, request.project_id),
            )
            last_extraction = extraction
            if extraction.payload is None:
                return self._human_review_report(
                    quality_report,
                    f"extractor_error: {extraction.error}",
                )
            consistency = self.consistency.check(
                request.project_id,
                request.chapter_seq,
                current.content,
                extraction=extraction.payload,
            )
            last_consistency = consistency
            return self._combine_reports(quality_report, consistency)

        reviser = self.reviser or LLMChapterReviser()

        def revise(
            current: ChapterInput, revision: RevisionRequest
        ) -> ChapterInput:
            revised = _clean_draft(reviser.revise(current, revision, context))
            if not revised:
                raise ValueError("reviser returned an empty chapter")
            return self._chapter_input(
                request, current.genre, revised
            )

        try:
            loop = self.quality_loop.run(chapter, review=review, revise=revise)
        except Exception as exc:  # noqa: BLE001 - surface as pipeline failure
            result.chapter = chapter
            result.error = f"pipeline_error: {exc}"
            return result

        result.chapter = loop.chapter
        result.quality = loop.report
        result.consistency = last_consistency
        result.extraction = last_extraction
        result.attempts = loop.attempts
        result.notes.extend(loop.report.notes)

        if loop.report.decision is not Decision.ACCEPT:
            self._save_chapter(
                request,
                loop.chapter,
                status="pending",
                score=loop.report.score,
                rewrite_count=loop.rewrite_count,
                summary=None,
            )
            result.status = "pending"
            return result

        extraction = last_extraction
        if extraction is None or extraction.payload is None:
            self._save_chapter(
                request,
                loop.chapter,
                status="pending",
                score=loop.report.score,
                rewrite_count=loop.rewrite_count,
                summary=None,
            )
            result.status = "pending"
            result.error = "accepted chapter has no extraction payload"
            return result

        # The extractor's apply() needs a chapter row; store the accepted draft
        # as pending first, then apply, then mark final without losing summary.
        self._save_chapter(
            request,
            loop.chapter,
            status="pending",
            score=loop.report.score,
            rewrite_count=loop.rewrite_count,
            summary=None,
        )
        preview = self.extractor.apply(
            self.store,
            request.project_id,
            request.chapter_seq,
            extraction.payload,
            dry_run=True,
        )
        if preview.error:
            result.applied = preview
            result.status = "pending"
            result.error = preview.error
            return result
        if preview.needs_review:
            # Do not write half a payload when any entry needs a human. The
            # pending chapter keeps the prose for review; memory stays clean.
            result.applied = ApplyResult(
                skipped=list(preview.skipped),
                needs_review=list(preview.needs_review),
                key_events=list(preview.key_events),
                notes=["dry_run: no memory writes"] + list(preview.notes),
            )
            result.status = "pending"
            result.notes.append(
                "extraction produced needs_review items; "
                "no memory writes applied"
            )
            return result
        applied = self.extractor.apply(
            self.store,
            request.project_id,
            request.chapter_seq,
            extraction.payload,
        )
        result.applied = applied
        if applied.error:
            result.status = "pending"
            result.error = applied.error
            return result
        if applied.needs_review:  # pragma: no cover - dry_run mirrors apply
            result.status = "pending"
            result.notes.append(
                "extraction produced needs_review items after dry-run; "
                "chapter not finalized"
            )
            return result

        current = self.store.get_chapter(
            request.project_id, request.chapter_seq
        )
        self._save_chapter(
            request,
            loop.chapter,
            status="final",
            score=loop.report.score,
            rewrite_count=loop.rewrite_count,
            summary=current.summary if current else None,
        )
        result.status = "final"
        return result

    def _chapter_input(
        self, request: GenerationRequest, genre: str, content: str
    ) -> ChapterInput:
        brief = request.character_brief or self._character_brief(
            request.project_id
        )
        return ChapterInput(
            content=content,
            project_id=request.project_id,
            chapter_seq=request.chapter_seq,
            genre=genre,
            outline=request.outline,
            character_brief=brief,
            style_constraints=request.style_constraints,
            target_words=request.target_words,
        )

    def _character_brief(self, project_id: str) -> str:
        characters = self.store.list_characters(project_id)
        return "；".join(
            f"{item.name}：{item.status or ('存活' if item.alive else '已死亡')}"
            for item in characters[:20]
        )

    def _save_chapter(
        self,
        request: GenerationRequest,
        chapter: ChapterInput,
        *,
        status: str,
        score: int | None,
        rewrite_count: int,
        summary: str | None,
    ) -> None:
        existing = self.store.get_chapter(
            request.project_id, request.chapter_seq
        )
        title = request.title or (
            existing.title if existing and existing.title else
            f"第{request.chapter_seq}章"
        )
        self.store.upsert_chapter(
            request.project_id,
            request.chapter_seq,
            status,
            title=title,
            content=chapter.content,
            summary=summary,
            score=score,
            rewrite_count=rewrite_count,
        )

    @staticmethod
    def _human_review_report(
        quality: QualityReport, note: str
    ) -> QualityReport:
        return QualityReport(
            passed=False,
            decision=Decision.HUMAN_REVIEW,
            failures=list(quality.failures),
            score=quality.score,
            dimensions=dict(quality.dimensions),
            reasons=dict(quality.reasons),
            notes=list(quality.notes) + [note],
        )

    @staticmethod
    def _combine_reports(
        quality: QualityReport, consistency: ConsistencyReport
    ) -> QualityReport:
        findings = list(quality.failures) + list(consistency.findings)
        has_blocker = any(
            finding.severity is Severity.BLOCKER for finding in findings
        )
        has_major = any(
            finding.severity is Severity.MAJOR
            for finding in consistency.findings
        )
        if quality.decision is Decision.HUMAN_REVIEW:
            decision = Decision.HUMAN_REVIEW
        elif has_blocker:
            decision = Decision.REWRITE
        elif has_major:
            # R04/R05/R06 are major: stop automatic repair and ask a human.
            decision = Decision.HUMAN_REVIEW
        else:
            # Minor findings (R07 overdue emotional debt) are reminders only.
            decision = quality.decision
        return QualityReport(
            passed=decision is Decision.ACCEPT,
            decision=decision,
            failures=findings,
            score=quality.score,
            dimensions=dict(quality.dimensions),
            reasons=dict(quality.reasons),
            notes=list(quality.notes)
            + [f"consistency: {consistency.decision}"],
        )


def _clean_draft(text: str) -> str:
    """Strip model-added fences/title lines without touching chapter prose."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:markdown|text)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    lines = text.splitlines()
    while lines and (
        not lines[0].strip()
        or lines[0].lstrip().startswith("#")
        or re.match(r"^第[一二三四五六七八九十百千\d]+章", lines[0].strip())
    ):
        lines.pop(0)
    return "\n".join(lines).strip()


def run_chapter(
    store: MemoryStore,
    request: GenerationRequest,
    *,
    writer: ChapterWriter | None = None,
    reviser: ChapterReviser | None = None,
    extractor: MemoryExtractor | None = None,
    consistency: ConsistencyEngine | None = None,
    quality: QualityAdapter | None = None,
    quality_mode: str = "rules",
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> PipelineResult:
    """Convenience wrapper for one chapter."""
    pipeline = ChapterPipeline(
        store,
        writer=writer,
        reviser=reviser,
        extractor=extractor,
        consistency=consistency,
        quality=quality,
        quality_mode=quality_mode,
        min_confidence=min_confidence,
    )
    return pipeline.run(request)
