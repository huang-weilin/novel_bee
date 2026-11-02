import json
import sqlite3
from pathlib import Path

import pytest

from novel_pipeline.memory import MemoryStore

EXPECTED_TABLES = {
    "projects",
    "chapters",
    "characters",
    "character_events",
    "ledger_items",
    "ledger_item_aliases",
    "ledger_info_gap",
    "foreshadowing",
    "emotional_threads",
    "world_rules",
    "quality_failures",
    "confirmations",
}


@pytest.fixture
def store() -> MemoryStore:
    with MemoryStore() as memory:
        yield memory


def test_schema_creates_expected_tables(store: MemoryStore) -> None:
    rows = store._conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    tables = {row["name"] for row in rows}

    assert EXPECTED_TABLES <= tables
    store.migrate()
    assert len(store.list_projects()) == 0


def test_project_and_chapter_roundtrip(store: MemoryStore) -> None:
    project = store.create_project("长夜", "仙侠", target_chapters=120)
    assert store.get_project(project.id) == project
    assert [row.id for row in store.list_projects()] == [project.id]

    first = store.upsert_chapter(
        project.id, 1, "planned", title="第一章", summary="初见"
    )
    updated = store.upsert_chapter(
        project.id,
        1,
        "final",
        title="第一章",
        content="正文",
        summary="定稿摘要",
        score=82,
        rewrite_count=1,
    )

    assert updated.id == first.id
    assert updated.status == "final"
    assert updated.content == "正文"
    assert updated.score == 82
    assert updated.rewrite_count == 1
    assert len(store.list_chapters(project.id)) == 1


def test_chapter_review_items_roundtrip_and_clear(store: MemoryStore) -> None:
    project = store.create_project("长夜", "仙侠")
    store.upsert_chapter(project.id, 1, "pending", content="正文")
    items = [
        {
            "kind": "character",
            "name": "王五",
            "reason": "unknown_character",
            "detail": {"status": "新角色"},
        }
    ]

    store.set_chapter_review(project.id, 1, items)
    saved = store.get_chapter(project.id, 1)
    assert saved is not None
    assert saved.review_json is not None
    assert json.loads(saved.review_json) == items

    store.upsert_chapter(project.id, 1, "final", content="正文")
    cleared = store.get_chapter(project.id, 1)
    assert cleared is not None
    assert cleared.review_json is None


def test_chapter_requires_existing_project(store: MemoryStore) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        store.upsert_chapter("missing-project", 1, "planned")


def test_schema_checks_reject_invalid_enum_values(store: MemoryStore) -> None:
    project = store.create_project("长夜", "仙侠")
    with pytest.raises(sqlite3.IntegrityError):
        store.upsert_chapter(project.id, 1, "unknown")

    foreshadowing = store.create_foreshadowing(project.id, "青铜钥匙", 1)
    with pytest.raises(sqlite3.IntegrityError):
        store.update_foreshadowing(foreshadowing.id, status="unknown")

    chapter = store.upsert_chapter(project.id, 2, "final")
    with pytest.raises(sqlite3.IntegrityError):
        store.add_quality_failure(chapter.id, "unknown", "R01", "blocker")
    with pytest.raises(sqlite3.IntegrityError):
        store.add_quality_failure(chapter.id, "consistency", "R01", "unknown")
    with pytest.raises(sqlite3.IntegrityError):
        store.add_confirmation(chapter.id, "unknown", "accept")


def test_character_upsert_and_events(store: MemoryStore) -> None:
    project = store.create_project("长夜", "仙侠")
    created = store.upsert_character(
        project.id,
        "张三",
        status="城主",
        core_attributes={"年龄": 30},
        first_chapter=1,
    )
    updated = store.upsert_character(
        project.id,
        "张三",
        alive=False,
        status="已死亡",
        core_attributes={"年龄": 30, "死因": "中毒"},
        last_chapter=3,
    )

    assert updated.id == created.id
    assert updated.alive is False
    assert updated.first_chapter == 1
    assert updated.last_chapter == 3
    assert updated.core_attributes["死因"] == "中毒"

    event = store.add_character_event(
        created.id, 3, "中毒身亡", story_time="第三日黄昏"
    )
    assert event.character_id == created.id
    assert store.list_character_events(created.id) == [event]


def test_ledger_adjustment_can_go_negative(store: MemoryStore) -> None:
    project = store.create_project("长夜", "仙侠")
    item = store.upsert_ledger_item(
        project.id, "回魂丹", quantity=2, unit="颗", updated_chapter=1
    )

    after = store.adjust_ledger(project.id, "回魂丹", -1, chapter_seq=2)

    assert after.id == item.id
    assert after.quantity == 1
    assert after.updated_chapter == 2

    overdrawn = store.adjust_ledger(project.id, "回魂丹", -5, chapter_seq=3)
    assert overdrawn.quantity == -4

    with pytest.raises(KeyError):
        store.adjust_ledger(project.id, "不存在", -1)


def test_item_alias_roundtrip(store: MemoryStore) -> None:
    project = store.create_project("长夜", "仙侠")
    store.upsert_ledger_item(project.id, "金疮药", quantity=2, unit="瓶")

    alias = store.upsert_item_alias(project.id, "青布小包", "金疮药")
    assert alias.alias == "青布小包"
    assert alias.canonical_name == "金疮药"
    assert store.get_item_alias(project.id, "青布小包") == alias
    assert store.list_item_aliases(project.id) == [alias]
    assert store.resolve_item_name(project.id, "青布小包") == "金疮药"
    assert store.resolve_item_name(project.id, "金疮药") == "金疮药"
    assert store.resolve_item_name(project.id, "不存在") is None

    updated = store.upsert_item_alias(project.id, " 青布小包 ", "金疮药")
    assert updated.alias == "青布小包"
    assert len(store.list_item_aliases(project.id)) == 1

    assert store.delete_item_alias(project.id, "青布小包") is True
    assert store.delete_item_alias(project.id, "青布小包") is False
    assert store.resolve_item_name(project.id, "青布小包") is None


def test_item_alias_rejects_bad_targets(store: MemoryStore) -> None:
    project = store.create_project("长夜", "仙侠")
    store.upsert_ledger_item(project.id, "金疮药", quantity=2)

    with pytest.raises(ValueError):
        store.upsert_item_alias(project.id, "金疮药", "金疮药")
    with pytest.raises(ValueError):
        store.upsert_item_alias(project.id, " ", "金疮药")
    with pytest.raises(KeyError):
        store.upsert_item_alias(project.id, "青布小包", "不存在")


def test_info_gap_upsert(store: MemoryStore) -> None:
    project = store.create_project("长夜", "仙侠")
    character = store.upsert_character(project.id, "张三")
    store.upsert_info_gap(
        project.id,
        character.id,
        known_facts=["城主认得路"],
        unknown_facts=["城主是内奸"],
        updated_chapter=2,
    )
    updated = store.upsert_info_gap(
        project.id,
        character.id,
        known_facts=["城主认得路", "地牢有暗门"],
        unknown_facts=["城主是内奸"],
        updated_chapter=4,
    )

    assert updated.updated_chapter == 4
    assert updated.known_facts[-1] == "地牢有暗门"
    assert updated.unknown_facts == ["城主是内奸"]


def test_foreshadowing_lifecycle(store: MemoryStore) -> None:
    project = store.create_project("长夜", "仙侠")
    planted = store.create_foreshadowing(
        project.id,
        "青铜钥匙",
        2,
        notes="第二章出现",
        importance=5,
        target_chapter=35,
        last_touched_chapter=2,
    )

    assert planted.importance == 5
    assert planted.target_chapter == 35
    assert planted.last_touched_chapter == 2
    assert store.find_foreshadowing(project.id, "青铜钥匙") == [planted]
    assert store.list_foreshadowing(project.id, status="planted") == [planted]

    advanced = store.update_foreshadowing(
        planted.id, last_touched_chapter=8, notes="第8章推进"
    )
    assert advanced.last_touched_chapter == 8

    resolved = store.update_foreshadowing(
        planted.id, status="resolved", resolved_chapter=9
    )
    assert resolved.status == "resolved"
    assert resolved.resolved_chapter == 9
    assert store.list_foreshadowing(project.id, status="planted") == []

    with pytest.raises(ValueError):
        store.create_foreshadowing(project.id, "非法重要度", 1, importance=6)


def test_emotional_thread_lifecycle(store: MemoryStore) -> None:
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
        last_touched_chapter=1,
        notes="第 1 章他独自引开追兵",
    )

    assert thread.kind == "apology"
    assert thread.status == "open"
    assert thread.importance == 5
    assert store.find_emotional_thread(
        project.id, "沈砚欠阿棠一个解释"
    ) == thread
    assert store.list_emotional_threads(project.id, status="open") == [
        thread
    ]

    advanced = store.update_emotional_thread(
        thread.id, last_touched_chapter=2, notes="第 2 章再次回避"
    )
    assert advanced.last_touched_chapter == 2
    assert advanced.notes == "第 2 章再次回避"

    paid = store.update_emotional_thread(thread.id, status="paid")
    assert paid.status == "paid"
    assert store.list_emotional_threads(project.id, status="open") == []

    with pytest.raises(ValueError):
        store.create_emotional_thread(
            project.id, "非法类型", "甲", "乙", 1, kind="revenge"
        )
    with pytest.raises(ValueError):
        store.create_emotional_thread(
            project.id, "非法重要度", "甲", "乙", 1, importance=6
        )


def test_world_rule_upsert_and_list(store: MemoryStore) -> None:
    project = store.create_project("长夜", "仙侠")

    created = store.upsert_world_rule(
        project.id,
        "灵力规则",
        "灵力不能凭空恢复",
        importance=5,
        source_chapter=1,
    )
    updated = store.upsert_world_rule(
        project.id,
        "灵力规则",
        "灵力只能通过休息恢复",
        importance=4,
        updated_chapter=3,
    )

    assert updated.id == created.id
    assert updated.content == "灵力只能通过休息恢复"
    assert updated.importance == 4
    assert updated.source_chapter == 1
    assert updated.updated_chapter == 3
    assert store.get_world_rule(project.id, "灵力规则") == updated
    assert store.list_world_rules(project.id, status="active") == [updated]


def test_migrate_adds_long_span_columns_to_old_database(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                genre TEXT NOT NULL,
                target_chapters INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE foreshadowing (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id),
                title TEXT NOT NULL,
                planted_chapter INTEGER NOT NULL,
                resolved_chapter INTEGER,
                status TEXT NOT NULL DEFAULT 'planted',
                notes TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO projects (id, title, genre) VALUES ('p1', '长夜', '仙侠')"
        )
        conn.execute(
            "INSERT INTO foreshadowing "
            "(id, project_id, title, planted_chapter) "
            "VALUES ('f1', 'p1', '青铜钥匙', 2)"
        )

    with MemoryStore(path) as store:
        item = store.get_foreshadowing("f1")
        assert store.list_world_rules("p1") == []

    assert item is not None
    assert item.importance == 1
    assert item.target_chapter is None
    assert item.last_touched_chapter is None


def test_quality_failures_and_confirmations(store: MemoryStore) -> None:
    project = store.create_project("长夜", "仙侠")
    chapter = store.upsert_chapter(project.id, 1, "pending")

    failure = store.add_quality_failure(
        chapter.id,
        "consistency",
        "R02",
        "blocker",
        evidence="回魂丹数量 -1",
    )
    confirmation = store.add_confirmation(chapter.id, "quality", "rejected")

    assert store.list_quality_failures(chapter.id) == [failure]
    assert failure.resolved is False
    assert confirmation.chapter_id == chapter.id
    assert confirmation.gate_type == "quality"


def test_postgres_migration_matches_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    sql = (root / "migrations" / "001_init.sql").read_text(encoding="utf-8")
    upgrade = (root / "migrations" / "002_long_span.sql").read_text(
        encoding="utf-8"
    )
    emotional = (root / "migrations" / "003_emotional_threads.sql").read_text(
        encoding="utf-8"
    )

    for table in EXPECTED_TABLES | {"schema_migrations"}:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    assert "jsonb" in sql
    assert "gen_random_uuid()" in sql
    assert "CREATE INDEX IF NOT EXISTS idx_chapters_project_seq" in sql
    assert "target_chapter int" in sql
    assert "ADD COLUMN IF NOT EXISTS importance" in upgrade
    assert "CREATE TABLE IF NOT EXISTS world_rules" in upgrade
    assert "CREATE TABLE IF NOT EXISTS emotional_threads" in emotional
    assert "target_payoff_chapter int" in emotional
    assert "idx_emotional_threads_project_status" in emotional
