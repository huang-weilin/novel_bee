"""Deterministic cross-chapter consistency rules R01-R07.

The engine runs before finalizing a chapter. It uses only the structured
memory and the current chapter text (plus the extractor payload when
available), so it costs zero LLM tokens.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..quality.models import RuleFinding, Severity
from .extractor import (
    DEFAULT_MIN_CONFIDENCE,
    ExtractionPayload,
    open_foreshadowing_match,
)
from .store import MemoryStore

# R01 only treats a dead character as present when the name is followed by an
# action or speech verb. A bare mention ("张三死后") is a flashback/reference,
# not an appearance.
_ACTION_PHRASES = (
    "说|问|答|笑道|冷笑|开口|道[：:，,\\s]"
    "|喊[道：:]|叫[道：:]|喊出声|叫出声"
    "|走进|走出|走向|走到|走了|走过|跑进|跑出|跑向|跑到|跑了|跑过"
    "|站起|起身|伸手|点头|摇头|看见|看到|望着|望向|看着|看向"
    "|听见|听到|叹气|看了看|看了一眼|望了望"
)

_TIME_ISO = re.compile(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})")
_TIME_DAY = re.compile(r"第?\s*(\d+)\s*[日天]")
_TIME_DAY_EN = re.compile(r"day\s*(\d+)", re.IGNORECASE)


@dataclass
class ConsistencyReport:
    findings: list[RuleFinding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def blockers(self) -> list[RuleFinding]:
        return [
            finding
            for finding in self.findings
            if finding.severity is Severity.BLOCKER
        ]

    @property
    def passed(self) -> bool:
        return not self.blockers

    @property
    def decision(self) -> str:
        if self.blockers:
            return "rewrite"
        # Minor findings are reminders (R07 overdue emotional debt); they do
        # not stop finalization. Major findings still need a human.
        if any(
            finding.severity is Severity.MAJOR for finding in self.findings
        ):
            return "human_review"
        return "accept"

    def to_dict(self) -> dict:
        return {
            "pass": self.passed,
            "decision": self.decision,
            "findings": [finding.to_dict() for finding in self.findings],
            "notes": list(self.notes),
        }


def _snippet(text: str, needle: str, radius: int = 30) -> str:
    index = text.find(needle)
    if index < 0:
        return ""
    start = max(0, index - radius)
    end = min(len(text), index + len(needle) + radius)
    return text[start:end].replace("\n", " ").strip()


def _paragraphs(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n\s*\n|\n", text) if part.strip()]


def _parse_story_time(text: str | None) -> tuple[str, tuple[int, ...]] | None:
    if not text:
        return None
    match = _TIME_ISO.search(text)
    if match:
        return ("date", tuple(int(group) for group in match.groups()))
    match = _TIME_DAY.search(text)
    if match:
        return ("day", (int(match.group(1)),))
    match = _TIME_DAY_EN.search(text)
    if match:
        return ("day", (int(match.group(1)),))
    return None


class ConsistencyEngine:
    def __init__(
        self,
        store: MemoryStore,
        *,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    ) -> None:
        self.store = store
        self.min_confidence = min_confidence

    def check(
        self,
        project_id: str,
        chapter_seq: int,
        content: str,
        *,
        extraction: ExtractionPayload | None = None,
    ) -> ConsistencyReport:
        report = ConsistencyReport()
        self._r01(project_id, chapter_seq, content, report)
        self._r02(project_id, report)
        self._r03(project_id, content, report)
        self._r04(project_id, extraction, report)
        self._r05(project_id, extraction, report)
        self._r06(
            project_id,
            chapter_seq,
            extraction,
            report,
            self.min_confidence,
        )
        self._r07(project_id, chapter_seq, report)

        report.findings.sort(
            key=lambda finding: (
                0 if finding.severity is Severity.BLOCKER else 1,
                finding.rule_id,
            )
        )
        return report

    def _r01(
        self,
        project_id: str,
        chapter_seq: int,
        content: str,
        report: ConsistencyReport,
    ) -> None:
        for character in self.store.list_characters(project_id):
            if character.alive:
                continue
            pattern = re.compile(
                rf"{re.escape(character.name)}.{{0,4}}(?:{_ACTION_PHRASES})"
            )
            match = pattern.search(content)
            if match is None:
                continue
            evidence = content[
                max(0, match.start() - 20) : min(
                    len(content), match.end() + 20
                )
            ].replace("\n", " ")
            report.findings.append(
                RuleFinding(
                    rule_id="R01",
                    severity=Severity.BLOCKER,
                    evidence=evidence.strip(),
                    suggestion=(
                        f"{character.name} 在结构化记忆中已死亡；"
                        "删除其出场，或先通过人工确认修改存活状态"
                    ),
                    metrics={
                        "character": character.name,
                        "chapter_seq": chapter_seq,
                    },
                )
            )

    def _r02(self, project_id: str, report: ConsistencyReport) -> None:
        for item in self.store.list_ledger_items(project_id):
            if item.quantity >= 0:
                continue
            report.findings.append(
                RuleFinding(
                    rule_id="R02",
                    severity=Severity.BLOCKER,
                    evidence=f"{item.name} 当前数量 {item.quantity:g}{item.unit or ''}",
                    suggestion=(
                        f"为 {item.name} 补充来源，或修正本章用量，"
                        "使数量不为负"
                    ),
                    metrics={
                        "item": item.name,
                        "quantity": item.quantity,
                    },
                )
            )

    def _r03(
        self,
        project_id: str,
        content: str,
        report: ConsistencyReport,
    ) -> None:
        paragraphs = _paragraphs(content)
        seen: set[tuple[str, str]] = set()
        for character in self.store.list_characters(project_id):
            gap = self.store.get_info_gap(project_id, character.id)
            if gap is None:
                continue
            known = set(gap.known_facts)
            for fact in gap.unknown_facts:
                fact = str(fact).strip()
                if not fact or fact in known:
                    continue
                if (character.name, fact) in seen:
                    continue
                for paragraph in paragraphs:
                    if character.name not in paragraph or fact not in paragraph:
                        continue
                    seen.add((character.name, fact))
                    report.findings.append(
                        RuleFinding(
                            rule_id="R03",
                            severity=Severity.BLOCKER,
                            evidence=_snippet(paragraph, fact),
                            suggestion=(
                                f"{character.name} 尚不知道「{fact}」；"
                                "改为让知情角色透露，或删除该信息"
                            ),
                            metrics={
                                "character": character.name,
                                "fact": fact,
                            },
                        )
                    )
                    break

    def _r04(
        self,
        project_id: str,
        extraction: ExtractionPayload | None,
        report: ConsistencyReport,
    ) -> None:
        if extraction is None:
            report.notes.append("R04 skipped: no extraction payload")
            return
        for update in extraction.foreshadowing:
            matches = self.store.find_foreshadowing(project_id, update.title)
            if update.thread_id:
                by_id = self.store.get_foreshadowing(update.thread_id)
                if by_id is not None and by_id.project_id == project_id:
                    matches = [by_id]
            statuses = {item.status for item in matches}
            if update.action == "plant":
                if "planted" in statuses:
                    report.findings.append(
                        RuleFinding(
                            rule_id="R04",
                            severity=Severity.MAJOR,
                            evidence=(
                                f"伏笔「{update.title}」已处于 planted 状态，"
                                "本章再次埋设"
                            ),
                            suggestion="合并重复伏笔，或改写为推进已有伏笔",
                            metrics={"title": update.title, "action": "plant"},
                        )
                    )
                elif "resolved" in statuses:
                    report.findings.append(
                        RuleFinding(
                            rule_id="R04",
                            severity=Severity.MAJOR,
                            evidence=(
                                f"伏笔「{update.title}」已回收，本章再次首次埋设"
                            ),
                            suggestion="改用新伏笔，或人工确认重置该伏笔状态",
                            metrics={"title": update.title, "action": "plant"},
                        )
                    )
            elif update.action == "advance" and "planted" not in statuses:
                report.findings.append(
                    RuleFinding(
                        rule_id="R04",
                        severity=Severity.MAJOR,
                        evidence=f"伏笔「{update.title}」未处于 planted 状态却尝试推进",
                        suggestion="先补埋设章节，或删除错误的推进动作",
                        metrics={"title": update.title, "action": "advance"},
                    )
                )
            elif update.action == "resolve" and "planted" not in statuses:
                report.findings.append(
                    RuleFinding(
                        rule_id="R04",
                        severity=Severity.MAJOR,
                        evidence=f"伏笔「{update.title}」未处于 planted 状态却尝试回收",
                        suggestion="先补埋设章节，或删除错误的回收动作",
                        metrics={"title": update.title, "action": "resolve"},
                    )
                )
            elif update.action == "abandon" and "planted" not in statuses:
                report.findings.append(
                    RuleFinding(
                        rule_id="R04",
                        severity=Severity.MAJOR,
                        evidence=f"伏笔「{update.title}」未处于 planted 状态却尝试放弃",
                        suggestion="确认伏笔名称，或删除错误的放弃动作",
                        metrics={"title": update.title, "action": "abandon"},
                    )
                )

    def _r05(
        self,
        project_id: str,
        extraction: ExtractionPayload | None,
        report: ConsistencyReport,
    ) -> None:
        if extraction is None:
            report.notes.append("R05 skipped: no extraction payload")
            return
        for update in extraction.character_updates:
            character = self.store.get_character(project_id, update.name)
            if character is None or not update.story_time:
                continue
            current = _parse_story_time(update.story_time)
            if current is None:
                continue
            events = self.store.list_character_events(character.id)
            previous_event = next(
                (event for event in reversed(events) if event.story_time),
                None,
            )
            previous = (
                _parse_story_time(previous_event.story_time)
                if previous_event
                else None
            )
            if previous is None or previous[0] != current[0]:
                continue
            if current[1] < previous[1]:
                report.findings.append(
                    RuleFinding(
                        rule_id="R05",
                        severity=Severity.MAJOR,
                        evidence=(
                            f"{update.name} 本章时间「{update.story_time}」"
                            f"早于上一事件时间"
                        ),
                        suggestion="调整故事内时间，或明确这是回忆/插叙",
                        metrics={
                            "character": update.name,
                            "previous_time": previous_event.story_time,
                            "current_time": update.story_time,
                        },
                    )
                )

    def _r06(
        self,
        project_id: str,
        chapter_seq: int,
        extraction: ExtractionPayload | None,
        report: ConsistencyReport,
        min_confidence: float,
    ) -> None:
        # Only suppress a warning when ``apply`` would actually close the
        # thread. Low-confidence updates are skipped there, and a valid
        # thread_id wins over the title; mirror both rules exactly.
        resolved_here: set[str] = set()
        if extraction is not None:
            for update in extraction.foreshadowing:
                if update.action not in ("resolve", "abandon"):
                    continue
                if update.confidence < min_confidence:
                    continue
                item = open_foreshadowing_match(
                    self.store, project_id, update
                )
                if item is not None:
                    resolved_here.add(item.id)

        for item in self.store.list_foreshadowing(
            project_id, status="planted"
        ):
            if item.target_chapter is None:
                continue
            if item.target_chapter >= chapter_seq:
                continue
            if item.id in resolved_here:
                continue
            report.findings.append(
                RuleFinding(
                    rule_id="R06",
                    severity=Severity.MAJOR,
                    evidence=(
                        f"伏笔「{item.title}」目标第 {item.target_chapter} 章回收，"
                        f"当前第 {chapter_seq} 章仍未回收"
                    ),
                    suggestion=(
                        "本章补回收，或人工调整 target_chapter / 将线索标记为放弃"
                    ),
                    metrics={
                        "title": item.title,
                        "target_chapter": item.target_chapter,
                        "chapter_seq": chapter_seq,
                    },
                )
            )

    def _r07(
        self,
        project_id: str,
        chapter_seq: int,
        report: ConsistencyReport,
    ) -> None:
        """Remind about overdue emotional debts without forcing a payoff.

        A debt may be delayed on purpose: the longer the reader waits, the
        stronger the payoff can be. R07 is minor, so it never blocks or asks
        for a human; it only keeps the debt visible in the report.
        """
        for item in self.store.list_emotional_threads(
            project_id, status="open"
        ):
            if item.target_payoff_chapter is None:
                continue
            if item.target_payoff_chapter >= chapter_seq:
                continue
            report.findings.append(
                RuleFinding(
                    rule_id="R07",
                    severity=Severity.MINOR,
                    evidence=(
                        f"情感债「{item.title}」目标第 "
                        f"{item.target_payoff_chapter} 章还，"
                        f"当前第 {chapter_seq} 章仍未还"
                    ),
                    suggestion=(
                        "按需推进或兑现；情感债可以故意拖，"
                        "也可以人工改目标章或标记为放弃"
                    ),
                    metrics={
                        "title": item.title,
                        "target_payoff_chapter": item.target_payoff_chapter,
                        "chapter_seq": chapter_seq,
                    },
                )
            )
