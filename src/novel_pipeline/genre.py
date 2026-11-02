"""Genre profiles: one engine, small per-genre strategy deltas.

The pipeline, memory schema, consistency rules, and quality gates are shared.
A profile only supplies prompt fragments and checklists: narrative rules,
contract lines, required scene-plan fields, quality notes, and extraction
focus. Unknown genres fall back to the default profile, so adding a genre
never forks the pipeline or changes old projects by accident.

Write new profiles by adding data here, not by branching in the pipeline. A
profile is not a setting bible; lore belongs in the project's structured
memory or outline.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GenreProfile:
    """Prompt-level strategy for one genre.

    ``scene_plan_required`` holds ``ScenePlan`` field names from
    ``novel_pipeline.planning.SCENE_FIELD_LABELS``. Unknown names are ignored,
    so a profile can be inspected without importing the planner.
    """

    key: str
    label: str
    aliases: tuple[str, ...] = ()
    narrative_rules: tuple[str, ...] = ()
    contract_rules: tuple[str, ...] = ()
    scene_plan_required: tuple[str, ...] = ()
    quality_notes: tuple[str, ...] = ()
    extraction_focus: tuple[str, ...] = ()

    def matches(self, genre: str) -> bool:
        target = genre.strip().casefold()
        if not target:
            return False
        names = (self.key, self.label, *self.aliases)
        return target in {name.strip().casefold() for name in names}

    def directive(self) -> str:
        """Rules appended to the system prompt for generation."""
        if not self.narrative_rules:
            return ""
        lines = ["【题材专项】"]
        lines.extend(f"- {rule}" for rule in self.narrative_rules)
        return "\n".join(lines)

    def self_check(self) -> str:
        """Checklist appended after the hard requirements."""
        if not self.quality_notes:
            return ""
        lines = ["【题材自检】"]
        lines.extend(f"- {note}" for note in self.quality_notes)
        return "\n".join(lines)


DEFAULT_PROFILE = GenreProfile(key="default", label="通用")


XIANXIA_COMEDY = GenreProfile(
    key="xianxia_comedy",
    label="仙侠喜剧",
    aliases=("修仙喜剧", "都市修仙", "仙侠现实向", "仙界职场"),
    narrative_rules=(
        (
            "先把人放进麻烦里：开篇写一个具体的人、他今天要办的事、"
            "办不成会失去什么；世界观、门派史和修炼等级往后放。"
        ),
        (
            "荒诞由制度一本正经地执行：用公文、合同、收费单、考核表和"
            "客服话术说荒唐事；叙述者不解释笑点，也不用网络梗代替笑点。"
        ),
        (
            "主角要有私心、恐惧和代价：他先是一个要吃饭、要养家、"
            "怕丢饭碗的普通人，再是“正义执行者”；让他算钱、犹豫、撒谎、后悔。"
        ),
        (
            "兑现可以小：退一次钱、识破一次话术、保住一个床位、"
            "被一个具体的人看见，都算赢；不要每章都封店打脸。"
        ),
        (
            "反派要有真实的权力：他能扣工资、改记录、卡床位、叫保安、"
            "让证人改口；主角赢一次要付一次代价。"
        ),
        (
            "情感落在具体物件和动作上：药钱、收据、鸡蛋、旧工牌、"
            "半张进货单；不要写“他感到愤怒/心酸”。"
        ),
        "章末先还一笔小债，再留一个更大的问题；更大的问题不能把本章的兑现吞掉。",
    ),
    contract_rules=(
        (
            "本章的赢面要具体：谁退了钱、谁停工、谁被看见、主角得到什么；"
            "不能只停在“他说得对”"
        ),
        "笑点让制度自己说，叙述者不解释；不用网络梗、谐音梗和作者吐槽撑场面",
        "主角的选择要付代价；如果这一章他什么都没失去，就不算兑现",
    ),
    scene_plan_required=(
        "opening_hook",
        "reader_promise",
        "suppression",
        "stakes",
        "payoff_tool",
        "payoff",
        "next_hook",
    ),
    quality_notes=(
        (
            "开篇三问：具体的人是谁？他今天要办什么事？办不成会失去什么？"
            "三问有一个答不上来，就重写开头。"
        ),
        (
            "本章兑现能不能落到一个可看见的结果？只有争吵、只有道理、"
            "只有“众人点头”，不算兑现。"
        ),
        (
            "主角有没有私心、恐惧或代价？如果他全程正确、全程不怕、"
            "什么都没失去，这个人物是工具人。"
        ),
        "荒诞是不是制度在执行？如果笑点靠叙述者解释、网络梗或角色降智，删掉重写。",
        "配角有没有自己的利益和怕处？不能只当观众、捧哏或被打脸的工具。",
        "章末的大问题是不是压过了本章的小兑现？如果是，把兑现写实，再留问题。",
    ),
    extraction_focus=("规则与收费", "承诺与欠债", "关键物件", "人物把柄/软肋"),
)


GUFENG_MYSTERY = GenreProfile(
    key="gufeng_mystery",
    label="古风悬疑",
    aliases=("古代悬疑", "权谋", "古风权谋", "古代权谋"),
    narrative_rules=(
        (
            "每章至少有一个可见线索被用上或被推翻；线索要长在场景里"
            "（物证、口供、账册、伤口、路程），不靠旁白补。"
        ),
        "先给一个小答案或小反转，再留更大的问题；不要整章只问不答。",
        "人物的动机落在利益、恐惧、亲情、旧债上；不写“天生邪恶”或“为了大局”的空话。",
        (
            "权力压制要具体：谁能调兵、谁能封卷、谁能让证人消失、"
            "谁卡着粮道；不要只写“气氛压抑”。"
        ),
        (
            "古风语域靠器物、礼数、称谓、公文和时间感；对白可以有潜台词，"
            "但不要所有人都像作者在说话。"
        ),
        "章末落在物证、动作或一句没说完的话上；不写总结和道理。",
    ),
    contract_rules=(
        "本章至少有一个线索被当场用上或被推翻",
        "至少给出一个小答案，再留一个更大的问题",
        "反派的压制要具体到权力、资源或人命，不靠“气氛”",
        "主要人物的动机要能落到利益、恐惧、亲情或旧债",
    ),
    scene_plan_required=(
        "goal",
        "obstacle",
        "stakes",
        "turn",
        "payoff",
        "next_hook",
    ),
    quality_notes=(
        "线索是否公平：读者回看前文能不能找到它，而不是章末天降。",
        "小答案是否真的回答了本章提出的某个问题。",
        "动机是否落到利益、恐惧、亲情或旧债，而不是“他就是坏”。",
        "古风语域是否统一：称谓、器物、礼数有没有现代词穿帮。",
        "章末留下的问题是否比本章的小答案更大，但没有吞掉它。",
    ),
    extraction_focus=("线索与物证", "人物关系与立场", "承诺与威胁", "时间线"),
)


URBAN_ROMANCE = GenreProfile(
    key="urban_romance",
    label="都市言情",
    aliases=("现代言情", "甜宠", "言情", "都市情感"),
    narrative_rules=(
        (
            "关系变化必须通过动作、距离、称呼、物件或一次选择发生；"
            "不要用旁白宣布“她心动了”。"
        ),
        "每章至少一次关系推进或后退，并写出代价：谁先低头、谁退了一步、谁错过了什么。",
        "对白留潜台词：人物说出口的话和真正想要的东西之间要有缝；不要把心里话全说完。",
        "情感爆发前先欠：一次失约、一句没说出口的话、一个被误会的动作；先欠再还。",
        (
            "主要人物各有声口：句长、称呼、直接程度、撒谎方式不同；"
            "不要所有人都用短句乒乓。"
        ),
        "章末落在未说出口的话、一个动作或一个物件上；不写“他们终于明白了爱情”。",
    ),
    contract_rules=(
        "本章关系要有一次可看见的推进或后退，不能只靠旁白说“关系变好了”",
        "情感释放用动作、台词或物件，不写“他很心动/难过/震惊”",
        "主要人物的对白要有潜台词，不能把心里话全说完",
    ),
    scene_plan_required=(
        "emotional_target",
        "setup",
        "turn",
        "release",
        "aftertaste",
        "debt_paid",
        "debt_opened",
    ),
    quality_notes=(
        "关系变化有没有动作/距离/称呼/物件支撑，而不是只有心理描写。",
        "对白有没有潜台词；人物是不是把真实意图全说完了。",
        "这一章的选择有没有代价；如果谁都没失去什么，情感就不算推进。",
        "有没有用旁白解释“她心动了/他明白了”，有就删。",
        "章末是否落在画面、动作或未说出口的话上。",
    ),
    extraction_focus=("关系状态与称呼变化", "承诺与误会", "情感债", "关键物件"),
)


_PROFILES: tuple[GenreProfile, ...] = (
    XIANXIA_COMEDY,
    GUFENG_MYSTERY,
    URBAN_ROMANCE,
)


def resolve_genre(genre: str | None) -> GenreProfile:
    """Return the matching profile, or the behavior-preserving default."""
    target = (genre or "").strip()
    if not target:
        return DEFAULT_PROFILE
    return next(
        (profile for profile in _PROFILES if profile.matches(target)),
        DEFAULT_PROFILE,
    )


def all_profiles() -> tuple[GenreProfile, ...]:
    """Default first, then the configured genres."""
    return (DEFAULT_PROFILE, *_PROFILES)
