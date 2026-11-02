from novel_pipeline.genre import (
    DEFAULT_PROFILE,
    GUFENG_MYSTERY,
    URBAN_ROMANCE,
    XIANXIA_COMEDY,
    all_profiles,
    resolve_genre,
)
from novel_pipeline.memory.context import ContextAssembler
from novel_pipeline.memory.extractor import MemoryContext, build_prompt
from novel_pipeline.memory.store import MemoryStore
from novel_pipeline.planning import ScenePlan
from novel_pipeline.quality.models import ChapterInput


def test_resolve_genre_matches_key_label_and_aliases() -> None:
    assert resolve_genre("xianxia_comedy") is XIANXIA_COMEDY
    assert resolve_genre("XIANXIA_COMEDY") is XIANXIA_COMEDY
    assert resolve_genre("仙侠喜剧") is XIANXIA_COMEDY
    assert resolve_genre(" 修仙喜剧 ") is XIANXIA_COMEDY
    assert resolve_genre("都市修仙") is XIANXIA_COMEDY
    assert resolve_genre("古风悬疑") is GUFENG_MYSTERY
    assert resolve_genre("甜宠") is URBAN_ROMANCE


def test_unknown_or_plain_genre_keeps_the_default_profile() -> None:
    # Plain "仙侠" is intentionally not an alias: existing projects keep the
    # behavior they had before genre profiles existed.
    assert resolve_genre("仙侠") is DEFAULT_PROFILE
    assert resolve_genre("科幻") is DEFAULT_PROFILE
    assert resolve_genre("") is DEFAULT_PROFILE
    assert resolve_genre(None) is DEFAULT_PROFILE


def test_profiles_have_unique_names() -> None:
    seen: dict[str, str] = {}
    for profile in all_profiles():
        for name in (profile.key, profile.label, *profile.aliases):
            normalized = name.strip().casefold()
            assert normalized not in seen, f"{name} duplicated"
            seen[normalized] = profile.key


def test_default_profile_adds_no_genre_prompt_blocks() -> None:
    assert DEFAULT_PROFILE.directive() == ""
    assert DEFAULT_PROFILE.self_check() == ""
    assert DEFAULT_PROFILE.scene_plan_required == ()
    assert DEFAULT_PROFILE.contract_rules == ()


def test_genre_profiles_supply_rules_checks_and_extraction_focus() -> None:
    for profile in (XIANXIA_COMEDY, GUFENG_MYSTERY, URBAN_ROMANCE):
        assert profile.narrative_rules
        assert profile.contract_rules
        assert profile.scene_plan_required
        assert profile.quality_notes
        assert profile.extraction_focus
        assert profile.directive().startswith("【题材专项】")
        assert profile.self_check().startswith("【题材自检】")


def test_scene_plan_reports_missing_required_fields() -> None:
    plan = ScenePlan(
        opening_hook="药钱一夜翻倍",
        payoff="医馆退回药钱",
    )

    missing = plan.missing_fields(XIANXIA_COMEDY.scene_plan_required)
    assert missing == [
        "reader_promise",
        "suppression",
        "stakes",
        "payoff_tool",
        "next_hook",
    ]

    prompt = plan.to_prompt(XIANXIA_COMEDY.scene_plan_required)
    assert "本题材必填" in prompt
    assert "未填" in prompt
    assert "开篇钩子（前 3 段）：药钱一夜翻倍" in prompt


def test_scene_plan_ignores_unknown_required_fields() -> None:
    plan = ScenePlan(goal="拿到城防图")
    assert plan.missing_fields(("not_a_field", "goal")) == []


def test_context_injects_genre_rules_and_required_scene_fields() -> None:
    store = MemoryStore()
    project = store.create_project("修仙界315", "修仙喜剧")

    context = ContextAssembler(store).build(
        project.id,
        1,
        outline="许青去医馆退药",
        scene_plan=ScenePlan(opening_hook="药钱一夜翻倍"),
    )

    system = context.sections["system"]
    assert "【题材专项】" in system
    assert "荒诞由制度" in system
    assert "【题材自检】" in system
    assert "本章的赢面要具体" in context.sections["contract"]
    assert "本题材必填" in context.sections["scene"]
    assert "未填" in context.sections["scene"]
    assert any(
        "missing required fields" in warning for warning in context.warnings
    )


def test_context_keeps_default_behavior_for_plain_genre() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")

    context = ContextAssembler(store).build(project.id, 1, outline="大纲")

    assert "【题材专项】" not in context.sections["system"]
    assert "本题材必填" not in context.sections["scene"]
    assert not any(
        "missing required fields" in warning for warning in context.warnings
    )


def test_extractor_prompt_adds_genre_extraction_focus() -> None:
    chapter = ChapterInput(
        content="许青把药盒放在柜台上。",
        chapter_seq=2,
        genre="仙侠喜剧",
        outline="退药",
    )
    prompt = build_prompt(chapter, MemoryContext())

    assert "题材关注" in prompt
    assert "规则与收费" in prompt
    assert "关键物件" in prompt


def test_extractor_prompt_has_no_focus_for_plain_genre() -> None:
    chapter = ChapterInput(
        content="许青把药盒放在柜台上。",
        chapter_seq=2,
        genre="仙侠",
        outline="退药",
    )
    assert "题材关注" not in build_prompt(chapter, MemoryContext())
