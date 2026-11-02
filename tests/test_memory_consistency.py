from novel_pipeline.memory.consistency import ConsistencyEngine
from novel_pipeline.memory.extractor import ExtractionPayload, MemoryExtractor
from novel_pipeline.memory.store import MemoryStore
from novel_pipeline.quality.models import Severity


def make_payload(**overrides) -> ExtractionPayload:
    data = {
        "character_updates": [],
        "item_usage": [],
        "info_gains": [],
        "foreshadowing": [],
        "chapter_summary": "摘要",
        "key_events": [],
    }
    data.update(overrides)
    return ExtractionPayload.model_validate(data)


def test_r01_blocks_dead_character_speaking_but_not_mentions() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    store.upsert_character(project.id, "张三", alive=False, status="已死亡")
    engine = ConsistencyEngine(store)

    mention = engine.check(project.id, 2, "李四说：张三已经死了。")
    assert mention.findings == []

    road = engine.check(project.id, 2, "张三的道路被雨水冲断。")
    assert road.findings == []

    corridor = engine.check(project.id, 2, "张三的走廊里堆着旧书。")
    assert corridor.findings == []

    dog = engine.check(project.id, 2, "张三的看门狗叫了一声。")
    assert dog.findings == []

    speaking = engine.check(project.id, 2, "张三说：我回来了。")
    assert speaking.findings[0].rule_id == "R01"
    assert speaking.findings[0].severity.value == "blocker"
    assert speaking.decision == "rewrite"
    assert speaking.passed is False


def test_r02_blocks_negative_ledger_item() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    item = store.upsert_ledger_item(project.id, "回魂丹", quantity=1)
    engine = ConsistencyEngine(store)

    assert engine.check(project.id, 1, "正文").findings == []

    store.adjust_ledger(project.id, "回魂丹", -2, chapter_seq=1)
    report = engine.check(project.id, 1, "正文")

    assert report.findings[0].rule_id == "R02"
    assert report.findings[0].severity.value == "blocker"
    assert report.findings[0].metrics["quantity"] == -1
    assert item.quantity == 1


def test_r03_blocks_unknown_fact_in_character_paragraph() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    character = store.upsert_character(project.id, "张三")
    store.upsert_info_gap(
        project.id,
        character.id,
        known_facts=["城主认得路"],
        unknown_facts=["城主是内奸"],
    )
    engine = ConsistencyEngine(store)

    safe = engine.check(project.id, 1, "李四说：城主是内奸。")
    assert safe.findings == []

    leak = engine.check(project.id, 1, "张三说：城主是内奸。")
    assert leak.findings[0].rule_id == "R03"
    assert leak.findings[0].severity.value == "blocker"
    assert "城主是内奸" in leak.findings[0].evidence


def test_r04_flags_illegal_foreshadowing_actions() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    planted = store.create_foreshadowing(project.id, "青铜钥匙", 1)
    resolved = store.create_foreshadowing(project.id, "断裂玉佩", 1)
    store.update_foreshadowing(resolved.id, status="resolved", resolved_chapter=2)
    engine = ConsistencyEngine(store)

    duplicate = engine.check(
        project.id,
        3,
        "正文",
        extraction=make_payload(
            foreshadowing=[
                {"action": "plant", "title": "青铜钥匙", "confidence": 0.9}
            ]
        ),
    )
    assert duplicate.findings[0].rule_id == "R04"
    assert duplicate.findings[0].severity.value == "major"
    assert duplicate.decision == "human_review"

    replant = engine.check(
        project.id,
        3,
        "正文",
        extraction=make_payload(
            foreshadowing=[
                {"action": "plant", "title": "断裂玉佩", "confidence": 0.9}
            ]
        ),
    )
    assert "已回收" in replant.findings[0].evidence

    missing = engine.check(
        project.id,
        3,
        "正文",
        extraction=make_payload(
            foreshadowing=[
                {"action": "resolve", "title": "不存在", "confidence": 0.9}
            ]
        ),
    )
    assert "未处于 planted" in missing.findings[0].evidence

    clean = engine.check(
        project.id,
        3,
        "正文",
        extraction=make_payload(
            foreshadowing=[
                {"action": "plant", "title": "新伏笔", "confidence": 0.9}
            ]
        ),
    )
    assert clean.findings == []
    assert planted.status == "planted"


def test_r05_flags_story_time_regression() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    character = store.upsert_character(project.id, "张三")
    store.add_character_event(
        character.id, 1, "初次登场", story_time="第5日"
    )
    engine = ConsistencyEngine(store)

    backwards = engine.check(
        project.id,
        2,
        "正文",
        extraction=make_payload(
            character_updates=[
                {"name": "张三", "story_time": "第3日", "confidence": 0.9}
            ]
        ),
    )
    assert backwards.findings[0].rule_id == "R05"
    assert backwards.findings[0].severity.value == "major"

    forwards = engine.check(
        project.id,
        2,
        "正文",
        extraction=make_payload(
            character_updates=[
                {"name": "张三", "story_time": "第8日", "confidence": 0.9}
            ]
        ),
    )
    assert forwards.findings == []

    free_text = engine.check(
        project.id,
        2,
        "正文",
        extraction=make_payload(
            character_updates=[
                {"name": "张三", "story_time": "很久以前", "confidence": 0.9}
            ]
        ),
    )
    assert free_text.findings == []


def test_r06_flags_overdue_thread_but_not_due_or_resolved() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    thread = store.create_foreshadowing(
        project.id, "青铜钥匙", 2, target_chapter=5
    )
    engine = ConsistencyEngine(store)

    assert engine.check(project.id, 5, "正文").findings == []

    resolved_here = engine.check(
        project.id,
        6,
        "正文",
        extraction=make_payload(
            foreshadowing=[
                {
                    "action": "resolve",
                    "title": "青铜钥匙",
                    "thread_id": thread.id,
                    "confidence": 0.9,
                }
            ]
        ),
    )
    assert resolved_here.findings == []

    overdue = engine.check(project.id, 6, "正文")
    assert overdue.findings[0].rule_id == "R06"
    assert overdue.findings[0].severity.value == "major"
    assert overdue.decision == "human_review"
    assert overdue.findings[0].metrics["target_chapter"] == 5

    store.update_foreshadowing(
        thread.id, status="resolved", resolved_chapter=6
    )
    assert engine.check(project.id, 7, "正文").findings == []


def test_r06_does_not_trust_low_confidence_resolution() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    store.upsert_chapter(project.id, 6, "final")
    thread = store.create_foreshadowing(
        project.id, "青铜钥匙", 2, target_chapter=5
    )
    engine = ConsistencyEngine(store)
    payload = make_payload(
        foreshadowing=[
            {
                "action": "resolve",
                "title": "青铜钥匙",
                "thread_id": thread.id,
                "confidence": 0.1,
            }
        ]
    )

    report = engine.check(project.id, 6, "正文", extraction=payload)

    assert report.findings[0].rule_id == "R06"
    assert report.findings[0].metrics["title"] == "青铜钥匙"
    applied = MemoryExtractor().apply(store, project.id, 6, payload)
    assert applied.skipped[0].reason == "low_confidence"
    assert store.get_foreshadowing(thread.id).status == "planted"


def test_r06_matches_thread_id_before_title() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    store.upsert_chapter(project.id, 6, "final")
    key = store.create_foreshadowing(
        project.id, "青铜钥匙", 2, target_chapter=5
    )
    other = store.create_foreshadowing(
        project.id, "钥匙下落", 2, target_chapter=5
    )
    engine = ConsistencyEngine(store)
    payload = make_payload(
        foreshadowing=[
            {
                "action": "resolve",
                "title": "钥匙下落",
                "thread_id": key.id,
                "confidence": 0.9,
            }
        ]
    )

    report = engine.check(project.id, 6, "正文", extraction=payload)

    flagged = [finding.metrics["title"] for finding in report.findings]
    assert flagged == ["钥匙下落"]
    MemoryExtractor().apply(store, project.id, 6, payload)
    assert store.get_foreshadowing(key.id).status == "resolved"
    assert store.get_foreshadowing(other.id).status == "planted"


def test_r06_abandon_suppresses_overdue_warning() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    store.upsert_chapter(project.id, 6, "final")
    thread = store.create_foreshadowing(
        project.id, "青铜钥匙", 2, target_chapter=5
    )
    engine = ConsistencyEngine(store)
    payload = make_payload(
        foreshadowing=[
            {
                "action": "abandon",
                "title": "青铜钥匙",
                "thread_id": thread.id,
                "confidence": 0.9,
            }
        ]
    )

    report = engine.check(project.id, 6, "正文", extraction=payload)

    assert report.findings == []
    applied = MemoryExtractor().apply(store, project.id, 6, payload)
    assert applied.foreshadowing == 1
    assert store.get_foreshadowing(thread.id).status == "abandoned"


def test_r04_advance_requires_open_thread() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    store.create_foreshadowing(project.id, "青铜钥匙", 1)
    engine = ConsistencyEngine(store)

    valid = engine.check(
        project.id,
        2,
        "正文",
        extraction=make_payload(
            foreshadowing=[
                {"action": "advance", "title": "青铜钥匙", "confidence": 0.9}
            ]
        ),
    )
    assert valid.findings == []

    missing = engine.check(
        project.id,
        3,
        "正文",
        extraction=make_payload(
            foreshadowing=[
                {"action": "advance", "title": "不存在", "confidence": 0.9}
            ]
        ),
    )
    assert missing.findings[0].rule_id == "R04"
    assert "推进" in missing.findings[0].evidence


def test_r07_reminds_overdue_emotional_debt_without_blocking() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    thread = store.create_emotional_thread(
        project.id,
        "沈砚欠阿棠一个解释",
        "沈砚",
        "阿棠",
        1,
        kind="apology",
        target_payoff_chapter=3,
        importance=5,
    )
    engine = ConsistencyEngine(store)

    due = engine.check(project.id, 3, "正文")
    assert due.findings == []
    assert due.decision == "accept"

    overdue = engine.check(project.id, 4, "正文")
    assert [finding.rule_id for finding in overdue.findings] == ["R07"]
    assert overdue.findings[0].severity is Severity.MINOR
    assert overdue.decision == "accept"
    assert "可以故意拖" in overdue.findings[0].suggestion

    store.update_emotional_thread(thread.id, status="paid")
    after_payoff = engine.check(project.id, 4, "正文")
    assert after_payoff.findings == []


def test_missing_extraction_notes_and_serialization() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    engine = ConsistencyEngine(store)

    report = engine.check(project.id, 1, "正文")
    payload = report.to_dict()

    assert payload["pass"] is True
    assert payload["decision"] == "accept"
    assert any("R04 skipped" in note for note in payload["notes"])
    assert any("R05 skipped" in note for note in payload["notes"])
