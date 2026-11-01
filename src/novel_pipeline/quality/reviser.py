"""LLM-backed revision action for the quality loop.

A revision is intentionally narrow: fix the listed failures, preserve plot,
characters and approximate length. The loop owns retry limits; this module
only turns a ``RevisionRequest`` into a new chapter.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace

from ..config import LLMConfig
from ..llm import LLMClient, LLMError
from .loop import RevisionRequest
from .models import ChapterInput, Decision

MAX_CONTENT_CHARS = 20_000

REVISER_SYSTEM = """你是网络小说的修订员。根据质量门给出的失败项修订正文。

要求：
1. 只修改失败项涉及的问题，保留原有情节、人物、场景和大致篇幅。
2. 不添加解释、标题、批注或 Markdown 代码块，直接输出修订后的正文。
3. rewrite 允许调整段落结构；polish 只做局部修改。
4. 修订后的正文必须仍是完整的一章，不要续写下一章。"""


class RevisionError(RuntimeError):
    """Raised when the reviser cannot produce usable chapter text."""


def build_revision_prompt(chapter: ChapterInput, request: RevisionRequest) -> str:
    failures = "\n".join(
        f"- [{finding.rule_id} {finding.severity.value}] {finding.evidence}"
        + (f"；建议：{finding.suggestion}" if finding.suggestion else "")
        for finding in request.failures
    ) or "- 无具体失败项，按整体质量分提升。"

    content = chapter.content
    if len(content) > MAX_CONTENT_CHARS:
        content = content[:MAX_CONTENT_CHARS]

    mode = "重写" if request.action is Decision.REWRITE else "局部打磨"
    return f"""修订方式：{mode}
修订原因：{request.reason}

失败项：
{failures}

【原文开始】
{content}
【原文结束】

请直接输出修订后的正文。"""


def clean_output(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:markdown|md|text)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    text = re.sub(r"^(修订后的正文|修订正文|正文)[:：]\s*", "", text)
    text = text.strip()
    if not text:
        raise RevisionError("reviser returned empty content")
    return text


class LLMReviser:
    def __init__(self, complete: Callable[[str], str] | None = None):
        self._complete = complete

    def _call(self, prompt: str) -> str:
        if self._complete is not None:
            return self._complete(prompt)
        client = LLMClient(LLMConfig.from_env())
        return client.complete(
            prompt,
            system=REVISER_SYSTEM,
            temperature=0.4,
            max_tokens=4096,
        )

    def revise(
        self,
        chapter: ChapterInput,
        request: RevisionRequest,
    ) -> ChapterInput:
        prompt = build_revision_prompt(chapter, request)
        try:
            content = clean_output(self._call(prompt))
        except LLMError as exc:
            raise RevisionError(str(exc)) from exc
        return replace(chapter, content=content)
