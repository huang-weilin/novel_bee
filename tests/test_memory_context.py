import pytest

from novel_pipeline.memory.context import (
    ContextAssembler,
    ContextBudget,
    estimate_tokens,
)
from novel_pipeline.memory.store import MemoryStore
from novel_pipeline.planning import ScenePlan


def seed_project(store: MemoryStore, chapter_count: int = 6) -> str:
    project = store.create_project("长夜", "仙侠")
    store.upsert_character(
        project.id, "张三", status="城主", core_attributes={"年龄": 30}
    )
    store.upsert_character(project.id, "李四", alive=False, status="已死亡")
    store.upsert_ledger_item(project.id, "回魂丹", quantity=2, unit="颗")
    store.create_foreshadowing(project.id, "青铜钥匙", 1, notes="能开地牢")
    for seq in range(1, chapter_count + 1):
        store.upsert_chapter(
            project.id,
            seq,
            "final",
            title=f"第{seq}章",
            summary=f"第{seq}章摘要。主角推进了第{seq}个线索。" + "细节" * 10,
        )
    return project.id


def test_estimate_tokens_for_empty_cjk_and_ascii() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("中文") == 2
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("中文abcd") == 3


def test_build_uses_fixed_section_order_and_recent_window() -> None:
    store = MemoryStore()
    project_id = seed_project(store)
    assembler = ContextAssembler(store)

    context = assembler.build(project_id, 6, outline="主角夜探地牢")

    assert list(context.sections) == [
        "system",
        "l0",
        "l1",
        "l2",
        "l3",
        "outline",
        "scene",
        "contract",
    ]
    assert "第 3 章" in context.sections["l2"]
    assert "第 4 章" in context.sections["l2"]
    assert "第 5 章" in context.sections["l2"]
    assert "第 2 章" not in context.sections["l2"]
    assert "第 1 章" in context.sections["l3"]
    assert "第 2 章" in context.sections["l3"]
    assert context.text.startswith("【系统设定】")
    assert "叙事镜头、连贯与人物声音" in context.sections["system"]
    assert "简洁不等于碎" in context.sections["system"]
    assert "每场戏有脊柱" in context.sections["system"]
    assert "每章至少有一次读者兑现" in context.sections["system"]
    assert "开篇先给一个具体的人" in context.sections["system"]
    assert "主角要有私心、恐惧和代价" in context.sections["system"]
    assert "主角夜探地牢" in context.sections["outline"]
    assert "本章场景卡" in context.sections["scene"]
    assert "未提供" in context.sections["scene"]
    assert "目标字数：约 2000 字" in context.sections["contract"]
    assert "章末用画面" in context.sections["contract"]
    assert "本章至少有一次读者兑现" in context.sections["contract"]
    assert "开篇先给一个具体的人" in context.sections["contract"]
    assert "主角要有私心、恐惧和代价" in context.sections["contract"]
    assert context.trimmed == []


def test_scene_plan_is_rendered_in_context() -> None:
    store = MemoryStore()
    project_id = seed_project(store)
    context = ContextAssembler(store).build(
        project_id,
        6,
        outline="主角夜探地牢",
        scene_plan=ScenePlan(
            goal="拿到城防图",
            obstacle="老周不肯交底",
            stakes="打草惊蛇",
            emotional_target="警惕→短暂信任",
            setup="老周三次回避钥匙来历",
            turn="沈砚不再逼问",
            release="老周主动说出换防时间",
            aftertaste="雨声盖住关门声",
            reader_promise="读者想看沈砚拿到一条能翻案的线索",
            payoff="老周交出半张图，并说出初七换防",
            payoff_type="识破/得到",
            next_hook="另半张图在城主府",
        ),
    )

    assert "拿到城防图" in context.sections["scene"]
    assert "警惕→短暂信任" in context.sections["scene"]
    assert "雨声盖住关门声" in context.sections["scene"]
    assert "读者想看沈砚拿到一条能翻案的线索" in context.sections["scene"]
    assert "老周交出半张图" in context.sections["scene"]
    assert "另半张图在城主府" in context.sections["scene"]


def test_l0_contains_structured_facts() -> None:
    store = MemoryStore()
    project_id = seed_project(store)
    assembler = ContextAssembler(store)

    context = assembler.build(project_id, 6, outline="大纲")

    assert "张三（存活）" in context.sections["l0"]
    assert "李四（已死亡）" in context.sections["l0"]
    assert "回魂丹：2颗" in context.sections["l0"]
    assert "青铜钥匙" in context.sections["l0"]
    assert "寿命" not in context.sections["l0"]


def test_trim_order_is_l3_then_l2_then_l1() -> None:
    store = MemoryStore()
    project_id = seed_project(store, chapter_count=8)
    for seq in range(1, 9):
        store.upsert_chapter(
            project_id,
            seq,
            "final",
            title=f"第{seq}章",
            summary="很长的摘要" * 40,
        )
    assembler = ContextAssembler(
        store,
        ContextBudget(soft_limit=500, warn_limit=600, hard_limit=700),
    )

    context = assembler.build(project_id, 8, outline="大纲")

    assert context.trimmed == ["l3", "l2:2", "l1"]
    assert context.sections["l0"]
    assert context.sections["l3"] == ""
    assert context.sections["l1"] == ""
    assert "第 6 章" in context.sections["l2"]
    assert "第 7 章" in context.sections["l2"]
    assert "第 5 章" not in context.sections["l2"]


def test_l0_is_never_trimmed_even_over_hard_limit() -> None:
    store = MemoryStore()
    project_id = seed_project(store, chapter_count=2)
    for index in range(30):
        store.upsert_character(
            project_id,
            f"角色{index}",
            status="很长的状态" * 10,
            core_attributes={"说明": "很长的属性" * 20},
        )
    assembler = ContextAssembler(
        store,
        ContextBudget(soft_limit=100, warn_limit=200, hard_limit=300),
    )

    context = assembler.build(project_id, 2, outline="大纲")

    assert context.sections["l0"]
    assert context.token_estimate > 300
    assert any("hard limit" in item for item in context.warnings)


def test_missing_summary_is_reported() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    store.upsert_chapter(project.id, 1, "final")
    assembler = ContextAssembler(store)

    context = assembler.build(project.id, 2, outline="大纲")

    assert any("without summary" in item for item in context.warnings)
    assert "（无摘要）" in context.sections["l2"]


def test_missing_project_raises() -> None:
    store = MemoryStore()
    assembler = ContextAssembler(store)

    with pytest.raises(KeyError):
        assembler.build("missing", 1, outline="大纲")


def test_invalid_budget_rejected() -> None:
    with pytest.raises(ValueError):
        ContextBudget(soft_limit=800, warn_limit=400, hard_limit=1000)
    with pytest.raises(ValueError):
        ContextBudget(l3_limit=-1)


def test_l0_and_l1_view_caps_bound_noisy_memory() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    character = store.upsert_character(
        project.id,
        "张三",
        status="很长的状态" * 20,
        core_attributes={f"键{index}": "值" * 40 for index in range(10)},
    )
    store.upsert_info_gap(
        project.id,
        character.id,
        known_facts=[f"旧事实{index}" for index in range(20)],
        unknown_facts=["城主是内奸", "地牢有暗门"],
    )
    for index in range(30):
        store.create_foreshadowing(
            project.id, f"伏笔{index:02d}", index + 1
        )

    context = ContextAssembler(store).build(project.id, 31, outline="大纲")

    l0 = context.sections["l0"]
    l1 = context.sections["l1"]
    assert "另有 8 项" in l0
    assert "另有 17 条已折叠" in l0
    assert "旧事实19" in l0
    assert "旧事实16" not in l0
    assert "城主是内奸" in l0
    assert "地牢有暗门" in l0
    assert "显示 8 条未回收" in l0
    assert "伏笔29" in l0
    assert "伏笔21" not in l0
    assert "另有 22 条未回收伏笔已折叠" in l1


def test_l0_entity_view_caps_fold_without_deleting() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    protagonist = store.upsert_character(
        project.id, "主角", last_chapter=100
    )
    for index in range(59):
        store.upsert_character(
            project.id,
            f"配角{index:02d}",
            last_chapter=index + 1,
        )
    for index in range(60):
        store.upsert_ledger_item(
            project.id,
            f"物品{index:02d}",
            quantity=1,
            updated_chapter=index + 1,
        )
    store.upsert_info_gap(
        project.id,
        protagonist.id,
        known_facts=["已知"],
        unknown_facts=[f"秘密{index}" for index in range(15)],
    )

    context = ContextAssembler(store).build(project.id, 100, outline="大纲")
    l0 = context.sections["l0"]

    assert "另有 10 个角色已折叠" in l0
    assert "另有 10 件物品已折叠" in l0
    assert "另有 5 条已折叠" in l0
    assert "配角58" in l0
    assert "配角00" not in l0
    assert "物品59" in l0
    assert "物品00" not in l0
    assert "秘密9" in l0
    assert "秘密10" not in l0
    assert len(store.list_characters(project.id)) == 60
    assert len(store.list_ledger_items(project.id)) == 60


def test_long_span_thread_survives_newest_window() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    for seq in range(1, 41):
        store.upsert_chapter(
            project.id, seq, "final", title=f"第{seq}章", summary="摘要。细节"
        )
    store.create_foreshadowing(
        project.id,
        "青铜钥匙",
        2,
        importance=5,
        target_chapter=35,
    )
    for index in range(30):
        store.create_foreshadowing(
            project.id, f"新线{index:02d}", 3 + index
        )
    assembler = ContextAssembler(store)

    high_importance = assembler.build(project.id, 21, outline="大纲")
    assert "青铜钥匙" in high_importance.sections["l1"]
    assert "重要度 5" in high_importance.sections["l1"]

    due_soon = assembler.build(project.id, 34, outline="大纲")
    assert "青铜钥匙" in due_soon.sections["l1"]
    assert "目标第 35 章" in due_soon.sections["l1"]

    overdue = assembler.build(project.id, 36, outline="大纲")
    assert "青铜钥匙" in overdue.sections["l1"]
    assert "已逾期" in overdue.sections["l1"]


def test_old_low_importance_thread_is_folded() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    for seq in range(1, 41):
        store.upsert_chapter(
            project.id, seq, "final", title=f"第{seq}章", summary="摘要。细节"
        )
    store.create_foreshadowing(project.id, "旧线", 2)
    for index in range(30):
        store.create_foreshadowing(
            project.id, f"新线{index:02d}", 3 + index
        )

    context = ContextAssembler(store).build(project.id, 34, outline="大纲")

    assert "旧线" not in context.sections["l1"]
    assert "另有" in context.sections["l1"]


def test_due_soon_low_importance_thread_is_selected() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    for seq in range(1, 41):
        store.upsert_chapter(
            project.id, seq, "final", title=f"第{seq}章", summary="摘要。细节"
        )
    store.create_foreshadowing(
        project.id, "到期旧线", 2, importance=1, target_chapter=20
    )
    for index in range(30):
        store.create_foreshadowing(
            project.id, f"新线{index:02d}", 3 + index
        )
    assembler = ContextAssembler(store)

    before_horizon = assembler.build(project.id, 16, outline="大纲")
    assert "到期旧线" not in before_horizon.sections["l1"]

    due_soon = assembler.build(project.id, 18, outline="大纲")
    assert "到期旧线" in due_soon.sections["l1"]
    assert "目标第 20 章" in due_soon.sections["l1"]


def test_recently_touched_low_importance_thread_is_selected() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    for seq in range(1, 41):
        store.upsert_chapter(
            project.id, seq, "final", title=f"第{seq}章", summary="摘要。细节"
        )
    store.create_foreshadowing(
        project.id,
        "刚推进的旧线",
        2,
        importance=1,
        last_touched_chapter=24,
    )
    for index in range(30):
        store.create_foreshadowing(
            project.id, f"新线{index:02d}", 3 + index
        )
    assembler = ContextAssembler(store)

    in_window = assembler.build(project.id, 25, outline="大纲")
    assert "刚推进的旧线" in in_window.sections["l1"]
    assert "最近推进第 24 章" in in_window.sections["l1"]

    out_of_window = assembler.build(project.id, 27, outline="大纲")
    assert "刚推进的旧线" not in out_of_window.sections["l1"]


def test_emotional_debt_survives_newest_window_and_is_excluded_when_paid() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    for seq in range(1, 41):
        store.upsert_chapter(
            project.id, seq, "final", title=f"第{seq}章", summary="摘要。细节"
        )
    main_debt = store.create_emotional_thread(
        project.id,
        "沈砚欠阿棠一个解释",
        "沈砚",
        "阿棠",
        2,
        kind="apology",
        importance=5,
        target_payoff_chapter=35,
        notes="第 1 章他丢下她独自引开追兵",
    )
    for index in range(30):
        store.create_emotional_thread(
            project.id,
            f"小债{index:02d}",
            "配角甲",
            "配角乙",
            3 + index,
        )
    assembler = ContextAssembler(store)

    high_importance = assembler.build(project.id, 21, outline="大纲")
    assert "沈砚欠阿棠一个解释" in high_importance.sections["l1"]
    assert "主债（重要度 5）" in high_importance.sections["l1"]
    assert "情感债：" in high_importance.sections["l0"]
    assert "显示 8 条于 L1" in high_importance.sections["l0"]

    due_soon = assembler.build(project.id, 34, outline="大纲")
    assert "目标第 35 章还" in due_soon.sections["l1"]

    overdue = assembler.build(project.id, 36, outline="大纲")
    assert "已到期（只提醒，可以故意拖）" in overdue.sections["l1"]

    store.update_emotional_thread(main_debt.id, status="paid")
    paid = assembler.build(project.id, 36, outline="大纲")
    assert "沈砚欠阿棠一个解释" not in paid.sections["l1"]


def test_world_rules_are_visible_clipped_and_capped() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    for index in range(10):
        store.upsert_world_rule(
            project.id,
            f"规则{index}",
            "长" * 100,
            importance=5 if index == 9 else 3,
            source_chapter=1,
        )

    context = ContextAssembler(store).build(project.id, 5, outline="大纲")
    l0 = context.sections["l0"]

    assert "世界规则" in l0
    assert "规则9" in l0
    assert "重要度 5" in l0
    assert "另有 2 条已折叠" in l0
    assert "长" * 60 in l0
    assert "长" * 61 not in l0


def test_l2_summary_is_clipped() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    store.upsert_chapter(project.id, 1, "final", summary="长" * 300)
    context = ContextAssembler(store).build(project.id, 2, outline="大纲")

    assert "长" * 100 + "…" in context.sections["l2"]
    assert "长" * 101 not in context.sections["l2"]


def test_invalid_zero_or_negative_view_caps_rejected() -> None:
    with pytest.raises(ValueError):
        ContextBudget(known_facts_shown=-1)
    with pytest.raises(ValueError):
        ContextBudget(characters_shown=-1)
    with pytest.raises(ValueError):
        ContextBudget(ledger_items_shown=-1)
    with pytest.raises(ValueError):
        ContextBudget(unknown_facts_shown=-1)
    with pytest.raises(ValueError):
        ContextBudget(foreshadowing_shown=-1)
    with pytest.raises(ValueError):
        ContextBudget(world_rules_shown=-1)
    with pytest.raises(ValueError):
        ContextBudget(foreshadowing_high_importance=6)
    with pytest.raises(ValueError):
        ContextBudget(emotional_threads_shown=-1)
    with pytest.raises(ValueError):
        ContextBudget(emotional_high_importance=6)


def test_l3_is_capped_for_long_books() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    for seq in range(1, 41):
        store.upsert_chapter(
            project.id, seq, "final", title=f"第{seq}章", summary="摘要。细节"
        )
    assembler = ContextAssembler(
        store,
        ContextBudget(
            soft_limit=100_000,
            warn_limit=100_001,
            hard_limit=100_002,
            l3_limit=5,
        ),
    )

    context = assembler.build(project.id, 41, outline="大纲")

    assert "更早的 32 章已折叠" in context.sections["l3"]
    assert "第 37 章" in context.sections["l3"]
    assert "第 32 章" not in context.sections["l3"]


def test_ten_chapter_growth_is_roughly_flat() -> None:
    store = MemoryStore()
    project_id = seed_project(store, chapter_count=10)
    assembler = ContextAssembler(store)

    outline = "主角夜探地牢，发现青铜钥匙与城主旧案有关。" * 10
    estimates = [
        assembler.build(project_id, seq, outline=outline).token_estimate
        for seq in range(1, 11)
    ]

    early = sum(estimates[:3]) / 3
    late = sum(estimates[-3:]) / 3
    assert late / early <= 1.3
