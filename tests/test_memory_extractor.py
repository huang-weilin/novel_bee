import json

import pytest

from novel_pipeline.memory.extractor import (
    ExtractionError,
    ExtractionPayload,
    MemoryContext,
    MemoryExtractor,
    build_prompt,
    parse_output,
)
from novel_pipeline.memory.store import MemoryStore
from novel_pipeline.quality.models import ChapterInput


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


def chapter(content: str = "张三走进大殿。") -> ChapterInput:
    return ChapterInput(
        content=content,
        project_id="p1",
        chapter_seq=1,
        genre="仙侠",
        outline="张三查案",
    )


def test_parse_output_accepts_code_fence_and_fields() -> None:
    raw = """```json
    {
      "character_updates": [
        {"name": "张三", "alive": false, "confidence": 0.9}
      ],
      "item_usage": [{"name": "回魂丹", "delta": -1}],
      "info_gains": [{"character": "张三", "facts": ["城主是内奸"]}],
      "foreshadowing": [{"action": "plant", "title": "青铜钥匙"}],
      "chapter_summary": "张三中毒身亡。",
      "key_events": ["张三身亡"]
    }
    ```"""
    payload = parse_output(raw)

    assert payload.character_updates[0].name == "张三"
    assert payload.item_usage[0].delta == -1


def test_parse_output_rejects_missing_top_level_field() -> None:
    data = {
        "character_updates": [],
        "item_usage": [],
        "info_gains": [],
        "foreshadowing": [],
        "chapter_summary": "摘要",
    }
    with pytest.raises(ExtractionError):
        parse_output(json.dumps(data, ensure_ascii=False))


def test_parse_output_rejects_unknown_field_and_long_summary() -> None:
    with pytest.raises(ExtractionError):
        parse_output(
            json.dumps(
                {
                    "character_updates": [],
                    "item_usage": [],
                    "info_gains": [],
                    "foreshadowing": [],
                    "chapter_summary": "摘要",
                    "key_events": [],
                    "extra": True,
                },
                ensure_ascii=False,
            )
        )

    with pytest.raises(ExtractionError):
        parse_output(
            json.dumps(
                {
                    "character_updates": [],
                    "item_usage": [],
                    "info_gains": [],
                    "foreshadowing": [],
                    "chapter_summary": "长" * 201,
                    "key_events": [],
                },
                ensure_ascii=False,
            )
        )


def test_build_prompt_contains_known_facts() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    character = store.upsert_character(project.id, "张三", status="城主")
    store.upsert_ledger_item(project.id, "回魂丹", quantity=2, unit="颗")
    store.create_foreshadowing(project.id, "青铜钥匙", 1)
    context = MemoryContext.from_store(store, project.id)

    prompt = build_prompt(chapter(), context)

    assert "张三" in prompt
    assert "回魂丹: 2颗" in prompt
    assert "青铜钥匙" in prompt
    assert "张三走进大殿。" in prompt
    assert character.alive is True


def test_extract_retries_after_validation_error() -> None:
    calls: list[str] = []
    valid = json.dumps(
        {
            "character_updates": [],
            "item_usage": [],
            "info_gains": [],
            "foreshadowing": [],
            "chapter_summary": "摘要",
            "key_events": [],
        },
        ensure_ascii=False,
    )

    def complete(prompt: str) -> str:
        calls.append(prompt)
        return "not json" if len(calls) == 1 else valid

    result = MemoryExtractor(complete=complete).extract(chapter())

    assert result.error is None
    assert result.payload is not None
    assert len(calls) == 2
    assert "上次输出校验失败" in calls[1]


def test_extract_returns_human_review_after_retries() -> None:
    result = MemoryExtractor(
        complete=lambda prompt: "not json", retries=0
    ).extract(chapter())

    assert result.human_review is True
    assert "JSON" in (result.error or "")


def test_empty_content_skips_llm() -> None:
    calls = []
    result = MemoryExtractor(
        complete=lambda prompt: calls.append(prompt) or "{}"
    ).extract(chapter("   "))

    assert result.human_review is True
    assert calls == []


def test_apply_updates_known_facts() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    store.upsert_chapter(project.id, 1, "final")
    character = store.upsert_character(
        project.id, "张三", status="城主", core_attributes={"年龄": 30}
    )
    store.upsert_ledger_item(project.id, "回魂丹", quantity=2, unit="颗")
    store.create_foreshadowing(project.id, "青铜钥匙", 1)
    store.upsert_info_gap(
        project.id,
        character.id,
        known_facts=["城主认得路"],
        unknown_facts=["城主是内奸"],
    )
    payload = make_payload(
        character_updates=[
            {
                "name": "张三",
                "alive": False,
                "status": "已死亡",
                "attributes_delta": {"死因": "中毒"},
                "event_summary": "中毒身亡",
                "story_time": "第三日黄昏",
                "confidence": 0.9,
            }
        ],
        item_usage=[
            {"name": "回魂丹", "delta": -1, "reason": "救人", "confidence": 0.9}
        ],
        info_gains=[
            {
                "character": "张三",
                "facts": ["城主是内奸", "地牢有暗门"],
                "confidence": 0.9,
            }
        ],
        foreshadowing=[
            {"action": "plant", "title": "断裂的玉佩", "confidence": 0.9},
            {"action": "resolve", "title": "青铜钥匙", "confidence": 0.9},
        ],
        chapter_summary="张三中毒，临死前指认城主。",
        key_events=["张三身亡"],
    )

    result = MemoryExtractor().apply(store, project.id, 1, payload)

    assert result.error is None
    assert result.character_updates == 1
    assert result.item_usage == 1
    assert result.info_gains == 1
    assert result.foreshadowing == 2
    assert result.needs_review == []

    updated = store.get_character(project.id, "张三")
    assert updated is not None
    assert updated.alive is False
    assert updated.core_attributes == {"年龄": 30, "死因": "中毒"}
    assert updated.last_chapter == 1
    assert store.get_ledger_item(project.id, "回魂丹").quantity == 1
    gap = store.get_info_gap(project.id, character.id)
    assert gap.known_facts == ["城主认得路", "城主是内奸", "地牢有暗门"]
    assert gap.unknown_facts == []
    assert store.find_foreshadowing(project.id, "断裂的玉佩")[0].status == "planted"
    assert store.find_foreshadowing(project.id, "青铜钥匙")[0].status == "resolved"
    assert store.get_chapter(project.id, 1).summary == "张三中毒，临死前指认城主。"
    assert store.list_character_events(character.id)[0].event_summary == "中毒身亡"


def test_apply_marks_unknown_and_low_confidence_without_writing() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    store.upsert_chapter(project.id, 1, "final")
    store.upsert_character(project.id, "张三", alive=True)
    store.upsert_ledger_item(project.id, "回魂丹", quantity=2)
    payload = make_payload(
        character_updates=[
            {"name": "李四", "confidence": 0.9},
            {"name": "张三", "alive": False, "confidence": 0.5},
        ],
        item_usage=[
            {"name": "不存在", "delta": -1, "confidence": 0.9},
            {"name": "回魂丹", "delta": -1, "confidence": 0.5},
        ],
        foreshadowing=[
            {"action": "resolve", "title": "不存在", "confidence": 0.9}
        ],
    )

    result = MemoryExtractor().apply(store, project.id, 1, payload)

    assert [item.reason for item in result.needs_review] == [
        "unknown_character",
        "unknown_item",
        "no_open_foreshadowing",
    ]
    assert len(result.skipped) == 2
    assert store.get_character(project.id, "李四") is None
    assert store.get_character(project.id, "张三").alive is True
    assert store.get_ledger_item(project.id, "回魂丹").quantity == 2


def test_apply_skips_partial_item_and_generic_roles() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    store.upsert_chapter(project.id, 1, "final")
    store.upsert_character(project.id, "沈砚")
    store.upsert_ledger_item(project.id, "城防图", quantity=1)
    store.upsert_ledger_item(project.id, "回魂丹", quantity=0)
    payload = make_payload(
        character_updates=[
            {"name": "蒙面人", "status": "追杀沈砚", "confidence": 0.9},
            {"name": "裴照", "status": "幕后主使", "confidence": 0.9},
        ],
        item_usage=[
            {
                "name": "城防图",
                "delta": 1,
                "reason": "老周交付半张城防图",
                "confidence": 0.9,
            },
            {
                "name": "城防图",
                "delta": 1,
                "action": "partial",
                "reason": "补上另一半",
                "confidence": 0.9,
            },
            {
                "name": "回魂丹",
                "delta": 1,
                "action": "gain",
                "reason": "获得一瓶",
                "confidence": 0.9,
            },
        ],
    )

    result = MemoryExtractor().apply(store, project.id, 1, payload)

    assert [item.name for item in result.needs_review] == ["裴照"]
    assert result.needs_review[0].reason == "unknown_character"
    assert [item.reason for item in result.skipped] == [
        "generic_role",
        "partial_item",
        "partial_item",
    ]
    assert store.get_character(project.id, "蒙面人") is None
    assert store.get_ledger_item(project.id, "城防图").quantity == 1
    assert store.get_ledger_item(project.id, "回魂丹").quantity == 1
    assert result.item_usage == 1


def test_apply_resolves_item_alias_before_updating() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    store.upsert_chapter(project.id, 1, "final")
    store.upsert_ledger_item(project.id, "金疮药", quantity=1, unit="瓶")
    store.upsert_item_alias(project.id, "青布小包", "金疮药")
    payload = make_payload(
        item_usage=[
            {
                "name": "青布小包",
                "delta": -1,
                "action": "consume",
                "reason": "给阿棠换药",
                "confidence": 0.9,
            }
        ],
    )

    result = MemoryExtractor().apply(store, project.id, 1, payload)

    assert result.item_usage == 1
    assert result.needs_review == []
    assert result.skipped == []
    assert store.get_ledger_item(project.id, "金疮药").quantity == 0
    assert any("resolved to 金疮药" in note for note in result.notes)


def test_apply_skips_negative_stock() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    store.upsert_chapter(project.id, 1, "final")
    store.upsert_ledger_item(project.id, "回魂丹", quantity=0, unit="颗")
    store.upsert_ledger_item(project.id, "灵石", quantity=1)
    payload = make_payload(
        item_usage=[
            {
                "name": "回魂丹",
                "delta": -1,
                "action": "consume",
                "confidence": 0.9,
            },
            {
                "name": "灵石",
                "delta": -2,
                "action": "transfer",
                "confidence": 0.9,
            },
        ],
    )

    result = MemoryExtractor().apply(store, project.id, 1, payload)

    assert result.item_usage == 0
    assert [item.reason for item in result.skipped] == [
        "negative_stock",
        "negative_stock",
    ]
    assert store.get_ledger_item(project.id, "回魂丹").quantity == 0
    assert store.get_ledger_item(project.id, "灵石").quantity == 1
    assert any("ledger unchanged" in note for note in result.notes)


def test_apply_dry_run_does_not_write_alias_or_stock() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    store.upsert_chapter(project.id, 1, "final")
    store.upsert_ledger_item(project.id, "金疮药", quantity=1)
    store.upsert_item_alias(project.id, "青布小包", "金疮药")
    payload = make_payload(
        item_usage=[
            {"name": "青布小包", "delta": -1, "confidence": 0.9}
        ],
    )

    result = MemoryExtractor().apply(
        store, project.id, 1, payload, dry_run=True
    )

    assert result.item_usage == 1
    assert store.get_ledger_item(project.id, "金疮药").quantity == 1


def test_apply_caps_noisy_updates() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    store.upsert_chapter(project.id, 1, "final")
    character = store.upsert_character(project.id, "张三")
    payload = make_payload(
        character_updates=[
            {
                "name": "张三",
                "status": "身份" * 100,
                "attributes_delta": {
                    f"键{index}": "值" * 100 for index in range(12)
                },
                "event_summary": "事件" * 100,
                "confidence": 0.9,
            }
        ],
        info_gains=[
            {
                "character": "张三",
                "facts": [
                    "城主是内奸",
                    "城主是内奸",
                    "地牢有暗门",
                    "粮草被调走",
                    "裴照在查案",
                    "老周隐瞒来历",
                ],
                "confidence": 0.9,
            }
        ],
        foreshadowing=[
            {"action": "plant", "title": f"伏笔{index}", "confidence": 0.9}
            for index in range(4)
        ],
    )

    result = MemoryExtractor().apply(store, project.id, 1, payload)

    updated = store.get_character(project.id, "张三")
    assert updated is not None
    assert len(updated.status) <= 80
    assert len(updated.core_attributes) == 8
    assert all(len(str(value)) <= 40 for value in updated.core_attributes.values())
    gap = store.get_info_gap(project.id, character.id)
    assert gap.known_facts == [
        "城主是内奸",
        "地牢有暗门",
        "粮草被调走",
        "裴照在查案",
        "老周隐瞒来历",
    ]
    assert result.foreshadowing == 2
    assert [item.reason for item in result.needs_review] == [
        "over_plant_budget",
        "over_plant_budget",
    ]
    assert any("attributes truncated" in note for note in result.notes)
    event = store.list_character_events(character.id)[0]
    assert len(event.event_summary) <= 160


def test_apply_rejects_duplicate_plant_and_missing_chapter() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    store.upsert_chapter(project.id, 1, "final")
    store.create_foreshadowing(project.id, "青铜钥匙", 1)
    payload = make_payload(
        foreshadowing=[
            {"action": "plant", "title": "青铜钥匙", "confidence": 0.9}
        ]
    )

    result = MemoryExtractor().apply(store, project.id, 1, payload)
    assert result.needs_review[0].reason == "foreshadowing_already_exists"

    missing = MemoryExtractor().apply(store, project.id, 99, payload)
    assert missing.error is not None
    assert missing.needs_review == []


def test_apply_plant_metadata_and_advance_by_thread_id() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    for seq in (1, 2, 3):
        store.upsert_chapter(project.id, seq, "final")
    extractor = MemoryExtractor()

    planted = make_payload(
        foreshadowing=[
            {
                "action": "plant",
                "title": "青铜钥匙",
                "importance": 5,
                "target_chapter": 35,
                "notes": "第二章出现",
                "confidence": 0.9,
            }
        ]
    )
    result = extractor.apply(store, project.id, 1, planted)
    assert result.needs_review == []
    item = store.find_foreshadowing(project.id, "青铜钥匙")[0]
    assert item.importance == 5
    assert item.target_chapter == 35
    assert item.last_touched_chapter == 1

    advanced = make_payload(
        foreshadowing=[
            {
                "action": "advance",
                "title": "钥匙下落",
                "thread_id": item.id,
                "notes": "第三章推进",
                "confidence": 0.9,
            }
        ]
    )
    result = extractor.apply(store, project.id, 2, advanced)
    assert result.needs_review == []
    item = store.get_foreshadowing(item.id)
    assert item is not None
    assert item.status == "planted"
    assert item.title == "青铜钥匙"
    assert item.last_touched_chapter == 2
    assert item.notes == "第三章推进"

    resolved = make_payload(
        foreshadowing=[
            {
                "action": "resolve",
                "title": "钥匙下落",
                "thread_id": item.id,
                "confidence": 0.9,
            }
        ]
    )
    result = extractor.apply(store, project.id, 3, resolved)
    assert result.needs_review == []
    item = store.get_foreshadowing(item.id)
    assert item is not None
    assert item.status == "resolved"
    assert item.resolved_chapter == 3
    assert item.last_touched_chapter == 3


def test_apply_abandon_closes_thread() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    store.upsert_chapter(project.id, 2, "final")
    thread = store.create_foreshadowing(
        project.id, "青铜钥匙", 1, target_chapter=5
    )
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

    result = MemoryExtractor().apply(store, project.id, 2, payload)

    updated = store.get_foreshadowing(thread.id)
    assert result.foreshadowing == 1
    assert updated is not None
    assert updated.status == "abandoned"
    assert updated.last_touched_chapter == 2


def test_apply_dry_run_validates_without_writing() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    store.upsert_chapter(project.id, 2, "pending")
    character = store.upsert_character(
        project.id, "张三", alive=True, core_attributes={"年龄": 30}
    )
    store.upsert_ledger_item(project.id, "回魂丹", quantity=2)
    thread = store.create_foreshadowing(project.id, "旧线", 1)
    store.upsert_info_gap(
        project.id, character.id, known_facts=["旧事实"], unknown_facts=["秘密"]
    )
    payload = make_payload(
        character_updates=[
            {"name": "张三", "alive": False, "status": "已死亡", "confidence": 0.9}
        ],
        item_usage=[{"name": "回魂丹", "delta": -1, "confidence": 0.9}],
        info_gains=[
            {"character": "张三", "facts": ["新事实"], "confidence": 0.9}
        ],
        foreshadowing=[
            {"action": "resolve", "title": "旧线", "confidence": 0.9},
            {"action": "plant", "title": "新线", "confidence": 0.9},
        ],
        chapter_summary="不应写入的摘要",
    )

    result = MemoryExtractor().apply(
        store, project.id, 2, payload, dry_run=True
    )

    assert result.error is None
    assert result.needs_review == []
    assert result.character_updates == 1
    assert result.item_usage == 1
    assert result.info_gains == 1
    assert result.foreshadowing == 2
    assert store.get_character(project.id, "张三").alive is True  # type: ignore[union-attr]
    assert store.get_ledger_item(project.id, "回魂丹").quantity == 2  # type: ignore[union-attr]
    assert store.get_foreshadowing(thread.id).status == "planted"  # type: ignore[union-attr]
    assert store.find_foreshadowing(project.id, "新线") == []
    assert store.get_info_gap(project.id, character.id).known_facts == ["旧事实"]  # type: ignore[union-attr]
    assert store.get_chapter(project.id, 2).summary is None  # type: ignore[union-attr]


def test_apply_caps_total_character_attributes() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    store.upsert_chapter(project.id, 1, "final")
    store.upsert_character(
        project.id,
        "张三",
        core_attributes={f"旧{index}": "值" for index in range(6)},
    )
    payload = make_payload(
        character_updates=[
            {
                "name": "张三",
                "attributes_delta": {
                    f"新{index}": "值" for index in range(8)
                },
                "confidence": 0.9,
            }
        ]
    )

    result = MemoryExtractor().apply(store, project.id, 1, payload)

    updated = store.get_character(project.id, "张三")
    assert updated is not None
    assert len(updated.core_attributes) == 8
    assert any("core attributes capped" in note for note in result.notes)


def test_apply_rejects_past_target_chapter() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    store.upsert_chapter(project.id, 1, "final")
    payload = make_payload(
        foreshadowing=[
            {
                "action": "plant",
                "title": "过期目标",
                "target_chapter": 1,
                "confidence": 0.9,
            }
        ]
    )

    result = MemoryExtractor().apply(store, project.id, 1, payload)

    assert result.needs_review[0].reason == "target_chapter_not_future"
    assert store.find_foreshadowing(project.id, "过期目标") == []


def test_prompt_lists_thread_id_and_target() -> None:
    store = MemoryStore()
    project = store.create_project("长夜", "仙侠")
    store.create_foreshadowing(
        project.id,
        "青铜钥匙",
        2,
        importance=5,
        target_chapter=35,
    )
    context = MemoryContext.from_store(store, project.id)

    prompt = build_prompt(chapter(), context)

    assert "id=" in prompt
    assert "重要度 5" in prompt
    assert "目标第 35 章" in prompt
