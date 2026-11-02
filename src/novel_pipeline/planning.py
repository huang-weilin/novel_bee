"""Optional scene plan for generation.

A scene plan is the smallest unit that connects plot to feeling: what the POV
character wants right now, what blocks them, what it costs to fail, what the
reader should feel, and how the beat is set up and released. The writer uses
it as a compact card; it is not a substitute for the chapter outline.

Two optional fields carry feeling across chapters: ``debt_paid`` names the
earlier promise this chapter pays off, and ``debt_opened`` names the new
promise it creates. This is not the full emotional ledger yet; it is a manual
hook so a writer can plan a payoff instead of only describing this chapter.

The payoff fields make the reader's desire explicit. A chapter can be
atmospheric, coherent, and still unreadable if nothing is won: the reader
needs a concrete thing to want, an unfair force holding it back, a tool the
story already planted, and a visible result. ``opening_hook`` is the first
three-paragraph promise; ``next_hook`` is the larger question left after the
small win, not a substitute for the win.

The fields are all optional so existing callers can omit the plan. When every
field is empty, the prompt asks the model to answer the same questions
internally instead of inventing them in the prose.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_SCENE_PROMPT = """【本章场景卡】
（未提供。写之前先在心里确定，不要输出：读者这一章最想看到什么赢面？谁或什么规则不公平地压住主角？主角用前文埋过的什么工具/信息/规则兑现？兑现后谁看见、谁被打脸、主角得到什么？本章先还哪笔小债，再留什么更大的问题？视角人物此刻想要什么？什么阻止他？失败或拒绝的代价是什么？本章情感从哪里蓄力、在哪里释放？）"""

SCENE_FIELD_LABELS: dict[str, str] = {
    "opening_hook": "开篇钩子（前 3 段）",
    "reader_promise": "读者这一章想看到的赢面",
    "suppression": "压制/不公平（谁或什么规则）",
    "goal": "视角人物此刻想要",
    "obstacle": "阻碍",
    "stakes": "失败/拒绝的代价",
    "payoff_tool": "兑现用的前文工具/信息/规则",
    "payoff": "本章兑现（谁被打脸/得到什么/谁看见）",
    "payoff_type": "兑现类型",
    "bystander_reaction": "旁观者反应",
    "next_hook": "兑现后更大的问题",
    "emotional_target": "情感任务（先→再）",
    "setup": "情感蓄力点",
    "turn": "转折/选择",
    "release": "释放方式",
    "aftertaste": "章末余韵",
    "debt_paid": "兑现的前文情感债",
    "debt_opened": "本章新欠下的情感债",
    "witnesses": "在场/缺席（爆发时谁看见）",
}


@dataclass(frozen=True)
class ScenePlan:
    goal: str = ""
    obstacle: str = ""
    stakes: str = ""
    emotional_target: str = ""
    setup: str = ""
    turn: str = ""
    release: str = ""
    aftertaste: str = ""
    debt_paid: str = ""
    debt_opened: str = ""
    witnesses: str = ""
    opening_hook: str = ""
    reader_promise: str = ""
    suppression: str = ""
    payoff_tool: str = ""
    payoff: str = ""
    payoff_type: str = ""
    bystander_reaction: str = ""
    next_hook: str = ""

    def is_empty(self) -> bool:
        return not any(
            value.strip()
            for value in (
                self.goal,
                self.obstacle,
                self.stakes,
                self.emotional_target,
                self.setup,
                self.turn,
                self.release,
                self.aftertaste,
                self.debt_paid,
                self.debt_opened,
                self.witnesses,
                self.opening_hook,
                self.reader_promise,
                self.suppression,
                self.payoff_tool,
                self.payoff,
                self.payoff_type,
                self.bystander_reaction,
                self.next_hook,
            )
        )

    def missing_fields(self, required: tuple[str, ...]) -> list[str]:
        """Return required field names that are blank or unknown."""
        return [
            name
            for name in required
            if name in SCENE_FIELD_LABELS and not getattr(self, name).strip()
        ]

    def to_prompt(self, required: tuple[str, ...] = ()) -> str:
        if self.is_empty():
            lines = [DEFAULT_SCENE_PROMPT]
        else:
            lines = ["【本章场景卡】"]
            for field_name, label in SCENE_FIELD_LABELS.items():
                value = getattr(self, field_name).strip()
                if value:
                    lines.append(f"- {label}：{value}")
        known_required = [
            name for name in required if name in SCENE_FIELD_LABELS
        ]
        if known_required:
            labels = "、".join(
                SCENE_FIELD_LABELS[name] for name in known_required
            )
            lines.append(f"本题材必填：{labels}。")
            missing = self.missing_fields(required)
            if missing:
                missing_labels = "、".join(
                    SCENE_FIELD_LABELS[name] for name in missing
                )
                lines.append(
                    f"未填：{missing_labels}。写正文前先在心里补全，"
                    "不要输出场景卡。"
                )
        return "\n".join(lines)
