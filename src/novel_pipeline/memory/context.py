"""Context Assembler for long-form generation.

Sections are rendered in a fixed order: system, L0 structured facts, L1 open
threads, L2 recent chapter summaries, L3 older one-line index, this chapter's
outline, and the output contract. L0 is never budget-trimmed; when the estimate
exceeds the soft limit the assembler drops L3 first, then reduces L2 to two
chapters, then drops L1.

L0 has fixed view caps (recent attributes, known facts, foreshadowing) so a
noisy extractor cannot make the prompt grow without bound. Unknown facts and
the open-thread counts are always shown in full.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

from ..genre import GenreProfile, resolve_genre
from ..planning import ScenePlan
from .models import Chapter, EmotionalThread, Foreshadowing
from .store import MemoryStore


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x3000 <= code <= 0x303F  # CJK punctuation
        or 0x3400 <= code <= 0x4DBF  # CJK extension A
        or 0x4E00 <= code <= 0x9FFF  # CJK unified ideographs
        or 0xFF00 <= code <= 0xFFEF  # fullwidth forms
    )


DEFAULT_NARRATIVE_RULES = """【叙事镜头、连贯与人物声音】
- 每段描写至少承担一项任务：交代空间、推进动作、暴露人物、埋线索、制造压力；一项都不占就删。
- 简洁不等于碎：动作峰值一句一个主要动作 + 一个必要结果；叙述、过渡、推理、情感段落可以连句成段，也可以短段推进。短段之间必须有局势、信息或关系的变化；不要整章只剩同一动作的 4-8 字碎片。
- 每场戏有脊柱：谁想要什么、什么阻止他、他做了什么选择、代价是什么、这场戏结束时局势变成什么样。每三到五段至少有一次局势、信息或关系变化。
- 每章至少有一次读者兑现：先让读者明确想看主角赢什么、被谁认可、出哪口气，再用前文埋过的工具、信息或规则把它兑现。兑现不一定是打脸；小胜、识破、得到、被认可、暖一次、笑一次都算。不能整章只查线索、只挨打、只留新问题。
- 兑现要具体：谁被打脸、主角得到什么、谁看见、代价是什么；不要用“众人震惊”“气氛一变”代替结果。章末可以留更大的问题，但本章要先还一笔小债。
- 爽点不能天降：兑现用的工具/信息必须在本章前段或前文出现过；主角可以输，但不能整章被动。赢要赢得有依据，输要输得有代价。
- 主角要有私心、恐惧和代价：他得先是一个想活下去、想护住某个人、想保住饭碗的普通人，不能只是替作者完成正义流程的工具人。
- 开篇先给一个具体的人和他眼前的具体麻烦：先让读者认识一个人、知道他怕失去什么，再展开世界观。不要先写典礼、天气、历史、群像或设定说明。第一段就要让读者产生一个“为什么/然后呢”的问题。
- 幽默/荒诞要一本正经：人物按世界内的规则认真执行，笑点来自规则与现实的错位，不靠网络梗、作者吐槽或角色降智。荒诞下面要有一件真事：穷、病、被欺负、被规则卡住。笑点不要由作者解释；让制度一本正经地说，让读者自己得出荒唐。
- 段落之间要有桥：时间桥（雨停之前）、空间桥（从后巷绕到东街）、因果桥（因为裴照那句话，他改了路）、人物桥（阿棠还在等他解释）。不要只靠空行跳切。
- 每个主要人物有自己的声口：句长、词汇、称呼、直接程度、关注点、撒谎方式不同；遮住名字，读者也应能大致认出谁在说。不要所有人物都短促寡言。
- 对话不是叙事全部：对话可以独立成段，只要每几句穿插动作、表情、空间或局势变化，就不是碎；不要连续十几段只有引号而没有场景推进。
- 限知视角可以写主角的判断、回忆、算计、自嘲；不是全知，也不是纯摄像机。不能写别人的心理，不能写作者式总结。
- 关键物件/问题要回指：在场景开头、转折、结尾各出现一次，让读者记得本章在追什么；回指要长在场景里，不要写前情提要。
- 情感靠“想要—受阻—代价—选择”积累；释放用动作、台词、反转或物件，不用解释；不写“他很愤怒/伤心/震惊”这类情绪标签。
- 情感/关系节点只留一个动作或一句台词；不要同时写走位、手势、眼神、心理和解释。动作戏的空间要清楚，情感戏的意图可以含蓄；读者能补的距离、关系、态度，不写满。
- 情感爆发靠“谁欠谁什么”积累；可以先还小债，不要把主债提前还完。重要人物在该出现的场合缺席，先让读者追问，再让他私下到场；不要用旁白替他解释。
- 按题材调语域：古风悬疑用器物、礼数、潜台词；都市用口语、反讽、内心账本；仙侠用意象但落在身体和目标；历史用制度、数字、官场潜台词；科幻用技术细节和系统逻辑；言情用小动作、距离和沉默。
- 章末落在画面、动作或未解问题上，不落在总结和道理上。"""


def estimate_tokens(text: str) -> int:
    """Conservative mixed Chinese/English token estimate.

    CJK characters count as one token each; other characters count as a
    quarter token. The value is intentionally approximate and only used for
    budgeting, never for billing.
    """
    if not text:
        return 0
    cjk = sum(1 for char in text if _is_cjk(char))
    other = len(text) - cjk
    return math.ceil(cjk + other / 4)


@dataclass(frozen=True)
class ContextBudget:
    soft_limit: int = 8000
    warn_limit: int = 10_000
    hard_limit: int = 12_000
    recent_chapters: int = 3
    l3_limit: int = 30
    status_chars: int = 40
    attributes_shown: int = 2
    attribute_value_chars: int = 24
    characters_shown: int = 50
    ledger_items_shown: int = 50
    known_facts_shown: int = 3
    unknown_facts_shown: int = 10
    foreshadowing_shown: int = 8
    foreshadowing_due_horizon: int = 3
    foreshadowing_high_importance: int = 4
    foreshadowing_recent_window: int = 2
    emotional_threads_shown: int = 8
    emotional_due_horizon: int = 3
    emotional_high_importance: int = 5
    emotional_recent_window: int = 2
    world_rules_shown: int = 8
    world_rule_chars: int = 60
    summary_chars: int = 100
    foreshadowing_note_chars: int = 30
    emotional_note_chars: int = 30

    def __post_init__(self) -> None:
        if not 0 < self.soft_limit <= self.warn_limit <= self.hard_limit:
            raise ValueError("budget limits must satisfy 0 < soft <= warn <= hard")
        for name in (
            "recent_chapters",
            "l3_limit",
            "status_chars",
            "attributes_shown",
            "attribute_value_chars",
            "characters_shown",
            "ledger_items_shown",
            "known_facts_shown",
            "unknown_facts_shown",
            "foreshadowing_shown",
            "foreshadowing_due_horizon",
            "foreshadowing_recent_window",
            "emotional_threads_shown",
            "emotional_due_horizon",
            "emotional_recent_window",
            "world_rules_shown",
            "world_rule_chars",
            "summary_chars",
            "foreshadowing_note_chars",
            "emotional_note_chars",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if not 1 <= self.foreshadowing_high_importance <= 5:
            raise ValueError(
                "foreshadowing_high_importance must be between 1 and 5"
            )
        if not 1 <= self.emotional_high_importance <= 5:
            raise ValueError(
                "emotional_high_importance must be between 1 and 5"
            )


@dataclass
class AssembledContext:
    text: str
    token_estimate: int
    sections: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    trimmed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "token_estimate": self.token_estimate,
            "sections": dict(self.sections),
            "warnings": list(self.warnings),
            "trimmed": list(self.trimmed),
        }


class ContextAssembler:
    def __init__(
        self,
        store: MemoryStore,
        budget: ContextBudget | None = None,
    ) -> None:
        self.store = store
        self.budget = budget or ContextBudget()

    def build(
        self,
        project_id: str,
        chapter_seq: int,
        *,
        outline: str,
        style_constraints: str = "",
        scene_plan: ScenePlan | None = None,
        target_words: int = 2000,
        pov: str = "第三人称",
    ) -> AssembledContext:
        project = self.store.get_project(project_id)
        if project is None:
            raise KeyError(f"project not found: {project_id}")
        profile = resolve_genre(project.genre)

        earlier = [
            chapter
            for chapter in self.store.list_chapters(project_id)
            if chapter.seq < chapter_seq
        ]
        recent_count = self.budget.recent_chapters
        recent = earlier[-recent_count:] if recent_count else []
        older = earlier[:-recent_count] if recent_count else earlier

        warnings: list[str] = []
        missing = [
            chapter.seq
            for chapter in earlier
            if not (chapter.summary or "").strip()
        ]
        if missing:
            warnings.append(f"chapters without summary: {missing}")
        if scene_plan is not None:
            missing_required = scene_plan.missing_fields(
                profile.scene_plan_required
            )
            if missing_required:
                warnings.append(
                    f"scene plan missing required fields for "
                    f"{profile.key}: {missing_required}"
                )

        sections: dict[str, str] = {
            "system": self._system(project.genre, style_constraints, profile),
            "l0": self._l0(project_id, chapter_seq),
            "l1": self._l1(project_id, chapter_seq),
            "l2": self._l2(recent),
            "l3": self._l3(older, self.budget.l3_limit),
            "outline": self._outline(outline),
            "scene": self._scene(scene_plan, profile.scene_plan_required),
            "contract": self._contract(target_words, pov, profile),
        }
        trimmed: list[str] = []
        text = self._render(sections)
        tokens = estimate_tokens(text)
        if tokens > self.budget.warn_limit:
            warnings.append(
                f"initial context estimate {tokens} exceeds warn limit "
                f"{self.budget.warn_limit}"
            )

        if tokens > self.budget.soft_limit:
            if sections["l3"]:
                sections["l3"] = ""
                trimmed.append("l3")
                tokens = self._recount(sections)

            if tokens > self.budget.soft_limit and len(recent) > 2:
                recent = recent[-2:]
                sections["l2"] = self._l2(recent)
                trimmed.append("l2:2")
                tokens = self._recount(sections)

            if tokens > self.budget.soft_limit and sections["l1"]:
                sections["l1"] = ""
                trimmed.append("l1")
                tokens = self._recount(sections)

        text = self._render(sections)
        tokens = estimate_tokens(text)
        if tokens > self.budget.hard_limit:
            warnings.append(
                f"context estimate {tokens} exceeds hard limit "
                f"{self.budget.hard_limit}; L0 was not trimmed"
            )
        elif tokens > self.budget.warn_limit:
            warnings.append(
                f"context estimate {tokens} exceeds warn limit "
                f"{self.budget.warn_limit}"
            )

        return AssembledContext(
            text=text,
            token_estimate=tokens,
            sections=sections,
            warnings=warnings,
            trimmed=trimmed,
        )

    def _recount(self, sections: dict[str, str]) -> int:
        return estimate_tokens(self._render(sections))

    @staticmethod
    def _render(sections: dict[str, str]) -> str:
        return "\n\n".join(
            section.strip() for section in sections.values() if section.strip()
        )

    @staticmethod
    def _system(
        genre: str,
        style_constraints: str,
        profile: GenreProfile,
    ) -> str:
        style = style_constraints.strip() or "（未提供）"
        parts = [
            f"""【系统设定】
你是一名中文网络小说作者，按给定大纲续写章节。
题材：{genre}
文风与禁忌：{style}

{DEFAULT_NARRATIVE_RULES}""",
            profile.directive(),
            """硬性要求：保持角色状态、物品数量、信息边界和伏笔状态一致；不引入未设定的事实；不复述设定卡。
通用质量要求：避免总结式收尾和情绪直给；不要让人物复述设定；段落长短要有变化；少用套话连接词。""",
            profile.self_check(),
        ]
        return "\n\n".join(part.strip() for part in parts if part.strip())

    def _select_foreshadowing(
        self, project_id: str, chapter_seq: int
    ) -> tuple[list[Foreshadowing], list[Foreshadowing]]:
        """Pick the threads the generation prompt must see.

        Storage keeps every thread. The prompt cannot, so the selection is:
        due soon (including overdue), high importance, recently touched, then
        newest. This lets a long-span thread survive after the newest-eight
        window has moved past it.
        """
        budget = self.budget
        items = [
            item
            for item in self.store.list_foreshadowing(project_id)
            if item.planted_chapter <= chapter_seq
        ]
        open_items = [item for item in items if item.status == "planted"]
        if not open_items or budget.foreshadowing_shown == 0:
            return [], open_items

        due = sorted(
            (
                item
                for item in open_items
                if item.target_chapter is not None
                and item.target_chapter
                <= chapter_seq + budget.foreshadowing_due_horizon
            ),
            key=lambda item: (
                item.target_chapter or 0,
                -item.importance,
                -item.planted_chapter,
                item.title,
            ),
        )
        high = sorted(
            (
                item
                for item in open_items
                if item.importance >= budget.foreshadowing_high_importance
            ),
            key=lambda item: (
                -item.importance,
                item.target_chapter or 10**9,
                -item.planted_chapter,
                item.title,
            ),
        )
        recent = sorted(
            (
                item
                for item in open_items
                if item.last_touched_chapter is not None
                and item.last_touched_chapter
                >= chapter_seq - budget.foreshadowing_recent_window
            ),
            key=lambda item: (
                -(item.last_touched_chapter or 0),
                -item.importance,
                -item.planted_chapter,
                item.title,
            ),
        )
        latest = sorted(
            open_items,
            key=lambda item: (
                -item.planted_chapter,
                -item.importance,
                item.title,
            ),
        )

        selected: list[Foreshadowing] = []
        seen: set[str] = set()
        for group in (due, high, recent, latest):
            for item in group:
                if item.id in seen:
                    continue
                selected.append(item)
                seen.add(item.id)
                if len(selected) >= budget.foreshadowing_shown:
                    return selected, open_items
        return selected, open_items

    def _fore_details(
        self,
        item: Foreshadowing,
        chapter_seq: int,
        *,
        include_status: bool,
    ) -> str:
        parts: list[str] = []
        if include_status:
            parts.append(item.status)
        parts.append(f"第 {item.planted_chapter} 章埋设")
        if item.importance > 1:
            parts.append(f"重要度 {item.importance}")
        if item.target_chapter is not None:
            target = f"目标第 {item.target_chapter} 章"
            if item.target_chapter < chapter_seq:
                target += "，已逾期"
            parts.append(target)
        if item.last_touched_chapter is not None:
            parts.append(f"最近推进第 {item.last_touched_chapter} 章")
        if item.notes:
            parts.append(_clip(item.notes, self.budget.foreshadowing_note_chars))
        return "；".join(parts)

    def _select_emotional_threads(
        self, project_id: str, chapter_seq: int
    ) -> tuple[list[EmotionalThread], list[EmotionalThread]]:
        """Pick open emotional debts the prompt must see.

        Same policy as foreshadowing except that an overdue debt is only a
        reminder. A debt may be deliberately delayed past its target; the
        selection keeps it visible instead of forcing a payoff.
        """
        budget = self.budget
        items = [
            item
            for item in self.store.list_emotional_threads(
                project_id, status="open"
            )
            if item.setup_chapter <= chapter_seq
        ]
        if not items or budget.emotional_threads_shown == 0:
            return [], items

        due = sorted(
            (
                item
                for item in items
                if item.target_payoff_chapter is not None
                and item.target_payoff_chapter
                <= chapter_seq + budget.emotional_due_horizon
            ),
            key=lambda item: (
                item.target_payoff_chapter or 0,
                -item.importance,
                -item.setup_chapter,
                item.title,
            ),
        )
        high = sorted(
            (
                item
                for item in items
                if item.importance >= budget.emotional_high_importance
            ),
            key=lambda item: (
                -item.importance,
                item.target_payoff_chapter or 10**9,
                -item.setup_chapter,
                item.title,
            ),
        )
        recent = sorted(
            (
                item
                for item in items
                if item.last_touched_chapter is not None
                and item.last_touched_chapter
                >= chapter_seq - budget.emotional_recent_window
            ),
            key=lambda item: (
                -(item.last_touched_chapter or 0),
                -item.importance,
                -item.setup_chapter,
                item.title,
            ),
        )
        latest = sorted(
            items,
            key=lambda item: (
                -item.setup_chapter,
                -item.importance,
                item.title,
            ),
        )

        selected: list[EmotionalThread] = []
        seen: set[str] = set()
        for group in (due, high, recent, latest):
            for item in group:
                if item.id in seen:
                    continue
                selected.append(item)
                seen.add(item.id)
                if len(selected) >= budget.emotional_threads_shown:
                    return selected, items
        return selected, items

    def _debt_details(
        self, item: EmotionalThread, chapter_seq: int
    ) -> str:
        parts = [f"{item.debt_from} → {item.debt_to}"]
        parts.append(f"第 {item.setup_chapter} 章欠下")
        if item.importance >= 5:
            parts.append("主债（重要度 5）")
        elif item.importance > 1:
            parts.append(f"重要度 {item.importance}")
        if item.target_payoff_chapter is not None:
            target = f"目标第 {item.target_payoff_chapter} 章还"
            if item.target_payoff_chapter < chapter_seq:
                target += "，已到期（只提醒，可以故意拖）"
            parts.append(target)
        if item.last_touched_chapter is not None:
            parts.append(f"最近推进第 {item.last_touched_chapter} 章")
        if item.notes:
            parts.append(_clip(item.notes, self.budget.emotional_note_chars))
        return "；".join(parts)

    def _l0(self, project_id: str, chapter_seq: int) -> str:
        characters = self.store.list_characters(project_id)
        ledger = self.store.list_ledger_items(project_id)
        foreshadowing = [
            item
            for item in self.store.list_foreshadowing(project_id)
            if item.planted_chapter <= chapter_seq
        ]
        rules = [
            item
            for item in self.store.list_world_rules(project_id, status="active")
            if item.source_chapter is None or item.source_chapter <= chapter_seq
        ]
        budget = self.budget

        ordered_characters = sorted(
            characters,
            key=lambda item: (
                -(item.last_chapter or 0),
                not item.alive,
                item.name,
            ),
        )
        shown_characters = (
            ordered_characters[: budget.characters_shown]
            if budget.characters_shown
            else []
        )
        omitted_characters = len(characters) - len(shown_characters)
        ordered_ledger = sorted(
            ledger,
            key=lambda item: (-(item.updated_chapter or 0), item.name),
        )
        shown_ledger = (
            ordered_ledger[: budget.ledger_items_shown]
            if budget.ledger_items_shown
            else []
        )
        omitted_items = len(ledger) - len(shown_ledger)

        character_lines = []
        for item in shown_characters:
            attributes = dict(
                list(item.core_attributes.items())[: budget.attributes_shown]
            )
            rendered_attributes = {
                key: _clip_value(value, budget.attribute_value_chars)
                for key, value in attributes.items()
            }
            attributes_text = json.dumps(rendered_attributes, ensure_ascii=False)
            omitted = len(item.core_attributes) - len(attributes)
            if omitted > 0:
                attributes_text += f"（另有 {omitted} 项）"
            character_lines.append(
                f"- {item.name}（{'存活' if item.alive else '已死亡'}）；"
                f"状态：{_clip(item.status or '未知', budget.status_chars)}；"
                f"属性：{attributes_text}；"
                f"出场：{item.first_chapter or '?'}-{item.last_chapter or '?'}"
            )
        if omitted_characters:
            character_lines.append(
                f"- （另有 {omitted_characters} 个角色已折叠，"
                "按最近出场优先）"
            )
        item_lines = [
            f"- {item.name}：{item.quantity:g}{item.unit or ''}"
            f"（更新于第 {item.updated_chapter or '?'} 章）"
            for item in shown_ledger
        ]
        if omitted_items:
            item_lines.append(
                f"- （另有 {omitted_items} 件物品已折叠，按最近更新优先）"
            )
        gap_lines = []
        for item in shown_characters:
            gap = self.store.get_info_gap(project_id, item.id)
            if gap is None:
                continue
            known = _tail(gap.known_facts, budget.known_facts_shown)
            known_text = json.dumps(known, ensure_ascii=False)
            omitted = len(gap.known_facts) - len(known)
            if omitted > 0:
                known_text += f"（另有 {omitted} 条已折叠）"
            unknown = (
                gap.unknown_facts[: budget.unknown_facts_shown]
                if budget.unknown_facts_shown
                else []
            )
            unknown_text = json.dumps(unknown, ensure_ascii=False)
            omitted_unknown = len(gap.unknown_facts) - len(unknown)
            if omitted_unknown > 0:
                unknown_text += f"（另有 {omitted_unknown} 条已折叠）"
            gap_lines.append(
                f"- {item.name}：已知 {known_text}；未知 {unknown_text}"
            )

        counts: dict[str, int] = {}
        for item in foreshadowing:
            counts[item.status] = counts.get(item.status, 0) + 1
        shown_fore, open_items = self._select_foreshadowing(
            project_id, chapter_seq
        )
        omitted_fore = len(open_items) - len(shown_fore)
        fore_header = ""
        if foreshadowing:
            fore_header = (
                f"（共 {len(foreshadowing)} 条："
                + " / ".join(f"{status} {count}" for status, count in counts.items())
                + f"；显示 {len(shown_fore)} 条未回收"
                "（优先到期/高重要/最近推进）"
                + (f"；另有 {omitted_fore} 条已折叠" if omitted_fore else "")
                + "）"
            )
        foreshadowing_lines = [
            f"- {item.title}："
            f"{self._fore_details(item, chapter_seq, include_status=True)}"
            for item in shown_fore
        ]

        shown_debts, open_debts = self._select_emotional_threads(
            project_id, chapter_seq
        )
        omitted_debts = len(open_debts) - len(shown_debts)
        if open_debts:
            debt_header = (
                f"（共 {len(open_debts)} 条未还；显示 {len(shown_debts)} 条于 L1"
                "（优先到期/主债/最近推进）"
                + (f"；另有 {omitted_debts} 条已折叠" if omitted_debts else "")
                + "）"
            )
        else:
            debt_header = "（无未还情感债）"

        shown_rules = rules[: budget.world_rules_shown]
        omitted_rules = len(rules) - len(shown_rules)
        rule_header = ""
        if rules:
            rule_header = (
                f"（共 {len(rules)} 条"
                + (f"；另有 {omitted_rules} 条已折叠" if omitted_rules else "")
                + "）"
            )
        rule_lines = [
            f"- {item.name}：{_clip(item.content, budget.world_rule_chars)}"
            f"（重要度 {item.importance}，第 {item.source_chapter or '?'} 章）"
            for item in shown_rules
        ]

        return f"""【L0 结构化记忆】
角色：
{_bullets(character_lines)}
物品：
{_bullets(item_lines)}
信息差：
{_bullets(gap_lines)}
世界规则：{rule_header}
{_bullets(rule_lines)}
伏笔：{fore_header}
{_bullets(foreshadowing_lines)}
情感债：{debt_header}"""

    def _l1(self, project_id: str, chapter_seq: int) -> str:
        shown, open_items = self._select_foreshadowing(
            project_id, chapter_seq
        )
        omitted = len(open_items) - len(shown)
        lines = []
        if not open_items:
            lines.append("- （无未回收伏笔）")
        else:
            if omitted > 0:
                lines.append(
                    f"- 另有 {omitted} 条未回收伏笔已折叠"
                    "（优先显示到期/高重要/最近推进）"
                )
            for item in shown:
                lines.append(
                    f"- {item.title}（"
                    f"{self._fore_details(item, chapter_seq, include_status=False)}）"
                )

        shown_debts, open_debts = self._select_emotional_threads(
            project_id, chapter_seq
        )
        debt_lines = []
        if not open_debts:
            debt_lines.append("- （无未还情感债）")
        else:
            omitted_debts = len(open_debts) - len(shown_debts)
            if omitted_debts:
                debt_lines.append(
                    f"- 另有 {omitted_debts} 条未还情感债已折叠"
                    "（优先显示到期/主债/最近推进）"
                )
            for item in shown_debts:
                debt_lines.append(
                    f"- {item.title}（"
                    f"{self._debt_details(item, chapter_seq)}）"
                )
        return f"""【L1 未解决线索与当前目标】
伏笔：
{_bullets(lines)}
情感债：
{_bullets(debt_lines)}"""

    def _l2(self, chapters: list[Chapter]) -> str:
        lines = []
        for chapter in chapters:
            title = f"《{chapter.title}》" if chapter.title else ""
            summary = (chapter.summary or "").strip() or "（无摘要）"
            summary = _clip(summary, self.budget.summary_chars)
            lines.append(f"- 第 {chapter.seq} 章{title}：{summary}")
        return f"""【L2 最近章节摘要】
{_bullets(lines)}"""

    @staticmethod
    def _l3(chapters: list[Chapter], limit: int) -> str:
        omitted = 0
        if limit and len(chapters) > limit:
            omitted = len(chapters) - limit
            chapters = chapters[-limit:]
        lines = []
        if omitted:
            lines.append(f"- 更早的 {omitted} 章已折叠，仅保留最近索引")
        for chapter in chapters:
            title = f"《{chapter.title}》" if chapter.title else ""
            summary = (chapter.summary or "").strip()
            one_line = summary.split("。", 1)[0][:40] if summary else "（无摘要）"
            lines.append(f"- 第 {chapter.seq} 章{title}：{one_line}")
        return f"""【L3 更早章节索引】
{_bullets(lines)}"""

    @staticmethod
    def _outline(outline: str) -> str:
        return f"""【本章大纲】
{outline.strip() or '（未提供）'}"""

    @staticmethod
    def _scene(
        scene_plan: ScenePlan | None,
        required: tuple[str, ...] = (),
    ) -> str:
        if scene_plan is None:
            return ScenePlan().to_prompt(required)
        return scene_plan.to_prompt(required)

    @staticmethod
    def _contract(
        target_words: int,
        pov: str,
        profile: GenreProfile,
    ) -> str:
        genre_rules = "".join(
            f"\n- {rule}" for rule in profile.contract_rules
        )
        return f"""【输出契约】
- 目标字数：约 {target_words} 字
- 视角：{pov}
- 开篇先给一个具体的人和他眼前的具体麻烦；不要先写典礼、天气、世界观、群像或设定说明
- 本章至少有一次读者兑现：用前文埋过的工具/规则，让主角赢一次、识破一次、得到一次、被认可一次，或让读者明确暖一次、笑一次；只留新问题不算兑现
- 兑现要具体到谁得到什么、谁看见、代价是什么；不要用“众人震惊”代替结果；不一定是打脸
- 主角要有私心、恐惧和代价，不能只是替作者完成正义流程的工具人
- 荒诞由制度一本正经地执行，笑点不靠作者解释，也不靠网络梗堆砌{genre_rules}
- 章末可以留更大的问题，但本章要先还一笔小债；不能连续多章只欠不还
- 按场景卡写：先让人物想要，再让阻碍生效，最后用动作、台词或反转释放，不靠解释
- 每场戏至少有一次局势、信息或关系变化；场景之间用时间/空间/因果/人物桥承接，不只靠空行
- 叙述、过渡、推理、情感段落要连句成段；动作峰值再拆短句。不要把整章写成动作提示或对话条
- 主要人物各有声口：句长、词汇、称呼、直接程度不同；对话前后有动作/环境/心理锚点
- 关键物件/问题在本章开头、转折、结尾至少回指一次
- 章末用画面、动作或未解问题收束，不写总结句
- 只输出本章正文；不要大纲、解释、Markdown 标题
- 不重复前文，不复述设定"""


def _bullets(lines: list[str]) -> str:
    return "\n".join(lines) if lines else "（无）"


def _tail(items: list, limit: int) -> list:
    return items[-limit:] if limit else []


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


def _clip_value(value: object, limit: int) -> str:
    if isinstance(value, str):
        return _clip(value, limit)
    return _clip(json.dumps(value, ensure_ascii=False), limit)
