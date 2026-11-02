import statistics

from novel_pipeline.memory.consistency import ConsistencyEngine
from novel_pipeline.memory.context import ContextAssembler
from novel_pipeline.memory.extractor import ExtractionPayload, MemoryExtractor
from novel_pipeline.memory.store import MemoryStore


def make_payload(**overrides) -> ExtractionPayload:
    data = {
        "character_updates": [],
        "item_usage": [],
        "info_gains": [],
        "foreshadowing": [],
        "chapter_summary": "本章摘要",
        "key_events": [],
    }
    data.update(overrides)
    return ExtractionPayload.model_validate(data)


def build_project(store: MemoryStore) -> str:
    project = store.create_project("长夜", "仙侠")
    for index in range(10):
        store.upsert_character(
            project.id,
            f"角色{index}",
            status="待命",
            core_attributes={"背景": "设定" * 10},
            first_chapter=1,
        )
    for index in range(10):
        store.upsert_ledger_item(
            project.id,
            f"物品{index}",
            quantity=100,
            unit="件",
            updated_chapter=1,
        )
    for index in range(10):
        store.create_foreshadowing(
            project.id, f"伏笔{index}", 1, notes="旧线索" * 8
        )
    for character in store.list_characters(project.id):
        store.upsert_info_gap(
            project.id,
            character.id,
            known_facts=["已知线索"],
            unknown_facts=[f"秘密{character.name}"],
            updated_chapter=1,
        )
    return project.id


def test_ten_chapter_regression_token_curve_and_blockers() -> None:
    store = MemoryStore()
    project_id = build_project(store)
    assembler = ContextAssembler(store)
    engine = ConsistencyEngine(store)
    extractor = MemoryExtractor()
    tokens: list[int] = []

    for seq in range(1, 11):
        context = assembler.build(
            project_id,
            seq,
            outline="角色0继续调查，遇到新的阻碍并发现线索。" * 4,
        )
        tokens.append(context.token_estimate)

        content = "角色0走进大殿。角色0说：继续查。"
        store.upsert_chapter(
            project_id, seq, "pending", title=f"第{seq}章", content=content
        )
        payload = make_payload(
            character_updates=[
                {
                    "name": "角色0",
                    "status": f"调查中{seq}",
                    "event_summary": f"第{seq}章推进",
                    "story_time": f"第{seq}日",
                    "confidence": 0.95,
                }
            ],
            item_usage=[
                {
                    "name": "物品0",
                    "delta": -1,
                    "reason": "本章消耗",
                    "confidence": 0.95,
                }
            ],
            chapter_summary=f"第{seq}章：角色0继续调查。",
            key_events=[f"事件{seq}"],
        )

        report = engine.check(
            project_id, seq, content, extraction=payload
        )
        assert report.blockers == []

        applied = extractor.apply(store, project_id, seq, payload)
        assert applied.error is None
        assert applied.needs_review == []

    early = statistics.fmean(tokens[:3])
    steady = statistics.fmean(tokens[3:6])
    late = statistics.fmean(tokens[-3:])

    assert late / early <= 1.3
    assert late / steady <= 1.1
    assert tokens[3] - tokens[2] >= tokens[-1] - tokens[-2]

    store.upsert_character(
        project_id, "角色1", alive=False, status="已死亡", last_chapter=10
    )
    dead_speaking = engine.check(project_id, 11, "角色1说：我回来了。")
    assert dead_speaking.decision == "rewrite"
    assert [finding.rule_id for finding in dead_speaking.blockers] == ["R01"]

    store.adjust_ledger(project_id, "物品1", -1000, chapter_seq=11)
    overused = engine.check(project_id, 11, "正文")
    assert "R02" in {finding.rule_id for finding in overused.blockers}

    leak = engine.check(project_id, 11, "角色2说：秘密角色2。")
    assert "R03" in {finding.rule_id for finding in leak.blockers}


def test_long_run_context_is_bounded_after_warmup() -> None:
    store = MemoryStore()
    project_id = build_project(store)
    assembler = ContextAssembler(store)
    extractor = MemoryExtractor()
    tokens: list[int] = []

    for seq in range(1, 41):
        context = assembler.build(
            project_id,
            seq,
            outline="角色0继续调查，遇到新的阻碍并发现线索。" * 4,
        )
        tokens.append(context.token_estimate)
        store.upsert_chapter(
            project_id, seq, "pending", title=f"第{seq}章", content="正文"
        )
        payload = make_payload(
            character_updates=[
                {
                    "name": f"角色{index}",
                    "status": f"调查中{seq}",
                    "attributes_delta": {f"线索{seq}": "新发现"},
                    "event_summary": f"第{seq}章推进",
                    "confidence": 0.95,
                }
                for index in range(3)
            ],
            info_gains=[
                {
                    "character": f"角色{index}",
                    "facts": [f"第{seq}章线索甲", f"第{seq}章线索乙"],
                    "confidence": 0.95,
                }
                for index in range(3)
            ],
            foreshadowing=[
                {
                    "action": "plant",
                    "title": f"新伏笔{seq}-{index}",
                    "notes": "待回收",
                    "confidence": 0.95,
                }
                for index in range(2)
            ],
            chapter_summary=f"第{seq}章：角色0继续调查。" + "细节" * 20,
            key_events=[f"事件{seq}"],
        )
        applied = extractor.apply(store, project_id, seq, payload)
        assert applied.error is None
        assert applied.needs_review == []

    mid = statistics.fmean(tokens[34:37])
    late = statistics.fmean(tokens[-3:])
    assert late / mid <= 1.05
    assert max(tokens[-5:]) - min(tokens[-5:]) <= 5
