"""SQLite-backed structured memory store.

Column names and constraints mirror PostgreSQL 16 (``migrations/001_init.sql``).
Only the physical types differ: TEXT stores UUIDs and JSON, INTEGER stores
booleans. Keeping the SQL here makes the production switch a driver-level
change rather than a rewrite of the M3 logic.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Self

from .models import (
    Chapter,
    Character,
    CharacterEvent,
    Confirmation,
    EmotionalThread,
    Foreshadowing,
    InfoGap,
    ItemAlias,
    LedgerItem,
    Project,
    QualityFailure,
    WorldRule,
)
from .schema import SQLITE_SCHEMA


class MemoryStore:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self.migrate()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def migrate(self) -> None:
        self._conn.executescript(SQLITE_SCHEMA)
        self._migrate_foreshadowing_columns()
        self._migrate_chapter_columns()
        self._conn.commit()

    def _migrate_chapter_columns(self) -> None:
        """Add pending-review JSON to databases created before T4-1c."""
        columns = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(chapters)")
        }
        if "review_json" not in columns:
            self._conn.execute(
                "ALTER TABLE chapters ADD COLUMN review_json TEXT"
            )

    def _migrate_foreshadowing_columns(self) -> None:
        """Add M3.5 columns to databases created before the columns existed.

        ``CREATE TABLE IF NOT EXISTS`` does not change an existing table, so the
        development adapter upgrades old local databases in place. PostgreSQL
        installations use ``migrations/002_long_span.sql`` instead.
        """
        columns = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(foreshadowing)")
        }
        additions = (
            ("importance", "INTEGER NOT NULL DEFAULT 1"),
            ("target_chapter", "INTEGER"),
            ("last_touched_chapter", "INTEGER"),
        )
        for name, ddl in additions:
            if name not in columns:
                self._conn.execute(
                    f"ALTER TABLE foreshadowing ADD COLUMN {name} {ddl}"
                )

    # -- projects ---------------------------------------------------------

    def create_project(
        self,
        title: str,
        genre: str,
        target_chapters: int | None = None,
        *,
        project_id: str | None = None,
    ) -> Project:
        pid = project_id or str(uuid.uuid4())
        with self._conn:
            self._conn.execute(
                "INSERT INTO projects (id, title, genre, target_chapters) "
                "VALUES (?, ?, ?, ?)",
                (pid, title, genre, target_chapters),
            )
        return self.get_project(pid)  # type: ignore[return-value]

    def get_project(self, project_id: str) -> Project | None:
        row = self._conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return Project.from_row(row) if row else None

    def list_projects(self) -> list[Project]:
        rows = self._conn.execute(
            "SELECT * FROM projects ORDER BY created_at, id"
        ).fetchall()
        return [Project.from_row(row) for row in rows]

    # -- chapters ---------------------------------------------------------

    def upsert_chapter(
        self,
        project_id: str,
        seq: int,
        status: str,
        *,
        title: str | None = None,
        content: str | None = None,
        summary: str | None = None,
        score: int | None = None,
        rewrite_count: int = 0,
        review_json: str | None = None,
        chapter_id: str | None = None,
    ) -> Chapter:
        cid = chapter_id or str(uuid.uuid4())
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO chapters (
                    id, project_id, seq, status, title, content, summary,
                    score, rewrite_count, review_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, seq) DO UPDATE SET
                    status = excluded.status,
                    title = excluded.title,
                    content = excluded.content,
                    summary = excluded.summary,
                    score = excluded.score,
                    rewrite_count = excluded.rewrite_count,
                    review_json = excluded.review_json
                """,
                (
                    cid,
                    project_id,
                    seq,
                    status,
                    title,
                    content,
                    summary,
                    score,
                    rewrite_count,
                    review_json,
                ),
            )
        return self.get_chapter(project_id, seq)  # type: ignore[return-value]

    def set_chapter_review(
        self,
        project_id: str,
        seq: int,
        items: list[dict] | None,
    ) -> None:
        """Persist the human-review items for a pending chapter."""
        review_json = (
            json.dumps(items, ensure_ascii=False) if items else None
        )
        with self._conn:
            self._conn.execute(
                "UPDATE chapters SET review_json = ? "
                "WHERE project_id = ? AND seq = ?",
                (review_json, project_id, seq),
            )

    def get_chapter(self, project_id: str, seq: int) -> Chapter | None:
        row = self._conn.execute(
            "SELECT * FROM chapters WHERE project_id = ? AND seq = ?",
            (project_id, seq),
        ).fetchone()
        return Chapter.from_row(row) if row else None

    def set_chapter_summary(
        self, project_id: str, seq: int, summary: str
    ) -> Chapter:
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE chapters SET summary = ? WHERE project_id = ? AND seq = ?",
                (summary, project_id, seq),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"chapter not found: {project_id}#{seq}")
        return self.get_chapter(project_id, seq)  # type: ignore[return-value]

    def get_chapter_by_id(self, chapter_id: str) -> Chapter | None:
        row = self._conn.execute(
            "SELECT * FROM chapters WHERE id = ?", (chapter_id,)
        ).fetchone()
        return Chapter.from_row(row) if row else None

    def list_chapters(self, project_id: str) -> list[Chapter]:
        rows = self._conn.execute(
            "SELECT * FROM chapters WHERE project_id = ? ORDER BY seq",
            (project_id,),
        ).fetchall()
        return [Chapter.from_row(row) for row in rows]

    # -- characters -------------------------------------------------------

    def upsert_character(
        self,
        project_id: str,
        name: str,
        *,
        alive: bool = True,
        status: str | None = None,
        core_attributes: dict | None = None,
        first_chapter: int | None = None,
        last_chapter: int | None = None,
        character_id: str | None = None,
    ) -> Character:
        cid = character_id or str(uuid.uuid4())
        attributes = json.dumps(core_attributes or {}, ensure_ascii=False)
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO characters (
                    id, project_id, name, alive, status, core_attributes,
                    first_chapter, last_chapter
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, name) DO UPDATE SET
                    alive = excluded.alive,
                    status = excluded.status,
                    core_attributes = excluded.core_attributes,
                    first_chapter = COALESCE(
                        characters.first_chapter, excluded.first_chapter
                    ),
                    last_chapter = excluded.last_chapter
                """,
                (
                    cid,
                    project_id,
                    name,
                    int(alive),
                    status,
                    attributes,
                    first_chapter,
                    last_chapter,
                ),
            )
        return self.get_character(project_id, name)  # type: ignore[return-value]

    def get_character(self, project_id: str, name: str) -> Character | None:
        row = self._conn.execute(
            "SELECT * FROM characters WHERE project_id = ? AND name = ?",
            (project_id, name),
        ).fetchone()
        return Character.from_row(row) if row else None

    def get_character_by_id(self, character_id: str) -> Character | None:
        row = self._conn.execute(
            "SELECT * FROM characters WHERE id = ?", (character_id,)
        ).fetchone()
        return Character.from_row(row) if row else None

    def list_characters(self, project_id: str) -> list[Character]:
        rows = self._conn.execute(
            "SELECT * FROM characters WHERE project_id = ? ORDER BY name",
            (project_id,),
        ).fetchall()
        return [Character.from_row(row) for row in rows]

    def add_character_event(
        self,
        character_id: str,
        chapter_seq: int,
        event_summary: str,
        *,
        story_time: str | None = None,
        event_id: str | None = None,
    ) -> CharacterEvent:
        eid = event_id or str(uuid.uuid4())
        with self._conn:
            self._conn.execute(
                "INSERT INTO character_events "
                "(id, character_id, chapter_seq, event_summary, story_time) "
                "VALUES (?, ?, ?, ?, ?)",
                (eid, character_id, chapter_seq, event_summary, story_time),
            )
        row = self._conn.execute(
            "SELECT * FROM character_events WHERE id = ?", (eid,)
        ).fetchone()
        return CharacterEvent.from_row(row)  # type: ignore[arg-type]

    def list_character_events(self, character_id: str) -> list[CharacterEvent]:
        rows = self._conn.execute(
            "SELECT * FROM character_events WHERE character_id = ? "
            "ORDER BY chapter_seq, created_at",
            (character_id,),
        ).fetchall()
        return [CharacterEvent.from_row(row) for row in rows]

    # -- ledger -----------------------------------------------------------

    def upsert_ledger_item(
        self,
        project_id: str,
        name: str,
        quantity: float = 0,
        *,
        unit: str | None = None,
        updated_chapter: int | None = None,
        item_id: str | None = None,
    ) -> LedgerItem:
        iid = item_id or str(uuid.uuid4())
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO ledger_items (
                    id, project_id, name, quantity, unit, updated_chapter
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, name) DO UPDATE SET
                    quantity = excluded.quantity,
                    unit = excluded.unit,
                    updated_chapter = excluded.updated_chapter
                """,
                (iid, project_id, name, quantity, unit, updated_chapter),
            )
        return self.get_ledger_item(project_id, name)  # type: ignore[return-value]

    def get_ledger_item(self, project_id: str, name: str) -> LedgerItem | None:
        row = self._conn.execute(
            "SELECT * FROM ledger_items WHERE project_id = ? AND name = ?",
            (project_id, name),
        ).fetchone()
        return LedgerItem.from_row(row) if row else None

    def list_ledger_items(self, project_id: str) -> list[LedgerItem]:
        rows = self._conn.execute(
            "SELECT * FROM ledger_items WHERE project_id = ? ORDER BY name",
            (project_id,),
        ).fetchall()
        return [LedgerItem.from_row(row) for row in rows]

    def adjust_ledger(
        self,
        project_id: str,
        name: str,
        delta: float,
        *,
        chapter_seq: int | None = None,
    ) -> LedgerItem:
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE ledger_items SET quantity = quantity + ?, "
                "updated_chapter = COALESCE(?, updated_chapter) "
                "WHERE project_id = ? AND name = ?",
                (delta, chapter_seq, project_id, name),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"ledger item not found: {name}")
        item = self.get_ledger_item(project_id, name)
        assert item is not None
        return item

    # -- ledger item aliases ----------------------------------------------

    def upsert_item_alias(
        self,
        project_id: str,
        alias: str,
        canonical_name: str,
    ) -> ItemAlias:
        alias = alias.strip()
        canonical_name = canonical_name.strip()
        if not alias or not canonical_name:
            raise ValueError("alias and canonical_name must not be empty")
        if alias == canonical_name:
            raise ValueError("alias must differ from canonical_name")
        if self.get_ledger_item(project_id, canonical_name) is None:
            raise KeyError(f"ledger item not found: {canonical_name}")
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO ledger_item_aliases (
                    project_id, alias, canonical_name
                ) VALUES (?, ?, ?)
                ON CONFLICT(project_id, alias) DO UPDATE SET
                    canonical_name = excluded.canonical_name
                """,
                (project_id, alias, canonical_name),
            )
        return self.get_item_alias(project_id, alias)  # type: ignore[return-value]

    def get_item_alias(
        self, project_id: str, alias: str
    ) -> ItemAlias | None:
        row = self._conn.execute(
            "SELECT * FROM ledger_item_aliases "
            "WHERE project_id = ? AND alias = ?",
            (project_id, alias.strip()),
        ).fetchone()
        return ItemAlias.from_row(row) if row else None

    def list_item_aliases(self, project_id: str) -> list[ItemAlias]:
        rows = self._conn.execute(
            "SELECT * FROM ledger_item_aliases WHERE project_id = ? "
            "ORDER BY alias",
            (project_id,),
        ).fetchall()
        return [ItemAlias.from_row(row) for row in rows]

    def delete_item_alias(self, project_id: str, alias: str) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "DELETE FROM ledger_item_aliases "
                "WHERE project_id = ? AND alias = ?",
                (project_id, alias.strip()),
            )
        return cursor.rowcount > 0

    def resolve_item_name(
        self, project_id: str, name: str
    ) -> str | None:
        """Return the canonical ledger name, following one alias hop."""
        name = name.strip()
        if not name:
            return None
        if self.get_ledger_item(project_id, name) is not None:
            return name
        alias = self.get_item_alias(project_id, name)
        if alias is None:
            return None
        if self.get_ledger_item(project_id, alias.canonical_name) is None:
            return None
        return alias.canonical_name

    # -- information gaps -------------------------------------------------

    def upsert_info_gap(
        self,
        project_id: str,
        character_id: str,
        known_facts: list,
        unknown_facts: list,
        *,
        updated_chapter: int | None = None,
        gap_id: str | None = None,
    ) -> InfoGap:
        gid = gap_id or str(uuid.uuid4())
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO ledger_info_gap (
                    id, project_id, character_id, known_facts, unknown_facts,
                    updated_chapter
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, character_id) DO UPDATE SET
                    known_facts = excluded.known_facts,
                    unknown_facts = excluded.unknown_facts,
                    updated_chapter = excluded.updated_chapter
                """,
                (
                    gid,
                    project_id,
                    character_id,
                    json.dumps(known_facts, ensure_ascii=False),
                    json.dumps(unknown_facts, ensure_ascii=False),
                    updated_chapter,
                ),
            )
        return self.get_info_gap(project_id, character_id)  # type: ignore[return-value]

    def get_info_gap(self, project_id: str, character_id: str) -> InfoGap | None:
        row = self._conn.execute(
            "SELECT * FROM ledger_info_gap "
            "WHERE project_id = ? AND character_id = ?",
            (project_id, character_id),
        ).fetchone()
        return InfoGap.from_row(row) if row else None

    # -- foreshadowing ----------------------------------------------------

    def create_foreshadowing(
        self,
        project_id: str,
        title: str,
        planted_chapter: int,
        *,
        status: str = "planted",
        resolved_chapter: int | None = None,
        notes: str | None = None,
        importance: int = 1,
        target_chapter: int | None = None,
        last_touched_chapter: int | None = None,
        foreshadowing_id: str | None = None,
    ) -> Foreshadowing:
        if not 1 <= importance <= 5:
            raise ValueError("importance must be between 1 and 5")
        fid = foreshadowing_id or str(uuid.uuid4())
        with self._conn:
            self._conn.execute(
                "INSERT INTO foreshadowing "
                "(id, project_id, title, planted_chapter, resolved_chapter, "
                "status, notes, importance, target_chapter, "
                "last_touched_chapter) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    fid,
                    project_id,
                    title,
                    planted_chapter,
                    resolved_chapter,
                    status,
                    notes,
                    importance,
                    target_chapter,
                    last_touched_chapter,
                ),
            )
        return self.get_foreshadowing(fid)  # type: ignore[return-value]

    def get_foreshadowing(self, foreshadowing_id: str) -> Foreshadowing | None:
        row = self._conn.execute(
            "SELECT * FROM foreshadowing WHERE id = ?", (foreshadowing_id,)
        ).fetchone()
        return Foreshadowing.from_row(row) if row else None

    def find_foreshadowing(
        self, project_id: str, title: str
    ) -> list[Foreshadowing]:
        rows = self._conn.execute(
            "SELECT * FROM foreshadowing WHERE project_id = ? AND title = ? "
            "ORDER BY planted_chapter",
            (project_id, title),
        ).fetchall()
        return [Foreshadowing.from_row(row) for row in rows]

    def list_foreshadowing(
        self, project_id: str, status: str | None = None
    ) -> list[Foreshadowing]:
        if status is None:
            rows = self._conn.execute(
                "SELECT * FROM foreshadowing WHERE project_id = ? "
                "ORDER BY planted_chapter, title",
                (project_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM foreshadowing WHERE project_id = ? AND status = ? "
                "ORDER BY planted_chapter, title",
                (project_id, status),
            ).fetchall()
        return [Foreshadowing.from_row(row) for row in rows]

    def update_foreshadowing(
        self,
        foreshadowing_id: str,
        *,
        status: str | None = None,
        resolved_chapter: int | None = None,
        notes: str | None = None,
        importance: int | None = None,
        target_chapter: int | None = None,
        last_touched_chapter: int | None = None,
    ) -> Foreshadowing:
        if importance is not None and not 1 <= importance <= 5:
            raise ValueError("importance must be between 1 and 5")
        parts: list[str] = []
        params: list[object] = []
        for column, value in (
            ("status", status),
            ("resolved_chapter", resolved_chapter),
            ("notes", notes),
            ("importance", importance),
            ("target_chapter", target_chapter),
            ("last_touched_chapter", last_touched_chapter),
        ):
            if value is not None:
                parts.append(f"{column} = ?")
                params.append(value)
        if not parts:
            raise ValueError("no foreshadowing fields to update")
        params.append(foreshadowing_id)
        with self._conn:
            cursor = self._conn.execute(
                f"UPDATE foreshadowing SET {', '.join(parts)} WHERE id = ?",
                params,
            )
            if cursor.rowcount == 0:
                raise KeyError(f"foreshadowing not found: {foreshadowing_id}")
        return self.get_foreshadowing(foreshadowing_id)  # type: ignore[return-value]

    # -- emotional threads ------------------------------------------------

    EMOTIONAL_KINDS = frozenset(
        {
            "approval",
            "apology",
            "belonging",
            "recognition",
            "rescue",
            "other",
        }
    )
    EMOTIONAL_STATUSES = frozenset({"open", "paid", "abandoned"})

    def create_emotional_thread(
        self,
        project_id: str,
        title: str,
        debt_from: str,
        debt_to: str,
        setup_chapter: int,
        *,
        kind: str = "other",
        target_payoff_chapter: int | None = None,
        status: str = "open",
        importance: int = 3,
        last_touched_chapter: int | None = None,
        notes: str | None = None,
        thread_id: str | None = None,
    ) -> EmotionalThread:
        if kind not in self.EMOTIONAL_KINDS:
            raise ValueError(f"unknown emotional thread kind: {kind}")
        if status not in self.EMOTIONAL_STATUSES:
            raise ValueError(f"unknown emotional thread status: {status}")
        if not 1 <= importance <= 5:
            raise ValueError("importance must be between 1 and 5")
        if setup_chapter < 1:
            raise ValueError("setup_chapter must be positive")
        if (
            target_payoff_chapter is not None
            and target_payoff_chapter < setup_chapter
        ):
            raise ValueError(
                "target_payoff_chapter must not be before setup_chapter"
            )
        tid = thread_id or str(uuid.uuid4())
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO emotional_threads (
                    id, project_id, title, debt_from, debt_to, kind,
                    setup_chapter, target_payoff_chapter, status, importance,
                    last_touched_chapter, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tid,
                    project_id,
                    title,
                    debt_from,
                    debt_to,
                    kind,
                    setup_chapter,
                    target_payoff_chapter,
                    status,
                    importance,
                    last_touched_chapter,
                    notes,
                ),
            )
        return self.get_emotional_thread(tid)  # type: ignore[return-value]

    def get_emotional_thread(
        self, thread_id: str
    ) -> EmotionalThread | None:
        row = self._conn.execute(
            "SELECT * FROM emotional_threads WHERE id = ?", (thread_id,)
        ).fetchone()
        return EmotionalThread.from_row(row) if row else None

    def find_emotional_thread(
        self, project_id: str, title: str
    ) -> EmotionalThread | None:
        row = self._conn.execute(
            "SELECT * FROM emotional_threads "
            "WHERE project_id = ? AND title = ?",
            (project_id, title),
        ).fetchone()
        return EmotionalThread.from_row(row) if row else None

    def list_emotional_threads(
        self, project_id: str, status: str | None = None
    ) -> list[EmotionalThread]:
        if status is None:
            rows = self._conn.execute(
                "SELECT * FROM emotional_threads WHERE project_id = ? "
                "ORDER BY setup_chapter, importance DESC, title",
                (project_id,),
            ).fetchall()
        else:
            if status not in self.EMOTIONAL_STATUSES:
                raise ValueError(f"unknown emotional thread status: {status}")
            rows = self._conn.execute(
                "SELECT * FROM emotional_threads "
                "WHERE project_id = ? AND status = ? "
                "ORDER BY setup_chapter, importance DESC, title",
                (project_id, status),
            ).fetchall()
        return [EmotionalThread.from_row(row) for row in rows]

    def update_emotional_thread(
        self,
        thread_id: str,
        *,
        title: str | None = None,
        status: str | None = None,
        target_payoff_chapter: int | None = None,
        importance: int | None = None,
        last_touched_chapter: int | None = None,
        notes: str | None = None,
    ) -> EmotionalThread:
        if status is not None and status not in self.EMOTIONAL_STATUSES:
            raise ValueError(f"unknown emotional thread status: {status}")
        if importance is not None and not 1 <= importance <= 5:
            raise ValueError("importance must be between 1 and 5")
        current = self.get_emotional_thread(thread_id)
        if current is None:
            raise KeyError(f"emotional thread not found: {thread_id}")
        if (
            target_payoff_chapter is not None
            and target_payoff_chapter < current.setup_chapter
        ):
            raise ValueError(
                "target_payoff_chapter must not be before setup_chapter"
            )
        parts: list[str] = []
        params: list[object] = []
        for column, value in (
            ("title", title),
            ("status", status),
            ("target_payoff_chapter", target_payoff_chapter),
            ("importance", importance),
            ("last_touched_chapter", last_touched_chapter),
            ("notes", notes),
        ):
            if value is not None:
                parts.append(f"{column} = ?")
                params.append(value)
        if not parts:
            raise ValueError("no emotional thread fields to update")
        params.append(thread_id)
        with self._conn:
            self._conn.execute(
                "UPDATE emotional_threads SET "
                f"{', '.join(parts)} WHERE id = ?",
                params,
            )
        return self.get_emotional_thread(thread_id)  # type: ignore[return-value]

    # -- world rules ------------------------------------------------------

    def upsert_world_rule(
        self,
        project_id: str,
        name: str,
        content: str,
        *,
        importance: int = 3,
        source_chapter: int | None = None,
        updated_chapter: int | None = None,
        status: str = "active",
        rule_id: str | None = None,
    ) -> WorldRule:
        if not 1 <= importance <= 5:
            raise ValueError("importance must be between 1 and 5")
        rid = rule_id or str(uuid.uuid4())
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO world_rules (
                    id, project_id, name, content, importance, source_chapter,
                    updated_chapter, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, name) DO UPDATE SET
                    content = excluded.content,
                    importance = excluded.importance,
                    source_chapter = COALESCE(
                        world_rules.source_chapter, excluded.source_chapter
                    ),
                    updated_chapter = excluded.updated_chapter,
                    status = excluded.status
                """,
                (
                    rid,
                    project_id,
                    name,
                    content,
                    importance,
                    source_chapter,
                    updated_chapter,
                    status,
                ),
            )
        return self.get_world_rule(project_id, name)  # type: ignore[return-value]

    def get_world_rule(self, project_id: str, name: str) -> WorldRule | None:
        row = self._conn.execute(
            "SELECT * FROM world_rules WHERE project_id = ? AND name = ?",
            (project_id, name),
        ).fetchone()
        return WorldRule.from_row(row) if row else None

    def list_world_rules(
        self, project_id: str, status: str | None = None
    ) -> list[WorldRule]:
        if status is None:
            rows = self._conn.execute(
                "SELECT * FROM world_rules WHERE project_id = ? "
                "ORDER BY importance DESC, source_chapter, name",
                (project_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM world_rules WHERE project_id = ? AND status = ? "
                "ORDER BY importance DESC, source_chapter, name",
                (project_id, status),
            ).fetchall()
        return [WorldRule.from_row(row) for row in rows]

    # -- quality failures / confirmations ---------------------------------

    def add_quality_failure(
        self,
        chapter_id: str,
        layer: str,
        rule_id: str,
        severity: str,
        *,
        evidence: str | None = None,
        resolved: bool = False,
        failure_id: str | None = None,
    ) -> QualityFailure:
        fid = failure_id or str(uuid.uuid4())
        with self._conn:
            self._conn.execute(
                "INSERT INTO quality_failures "
                "(id, chapter_id, layer, rule_id, severity, evidence, resolved) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    fid,
                    chapter_id,
                    layer,
                    rule_id,
                    severity,
                    evidence,
                    int(resolved),
                ),
            )
        row = self._conn.execute(
            "SELECT * FROM quality_failures WHERE id = ?", (fid,)
        ).fetchone()
        return QualityFailure.from_row(row)  # type: ignore[arg-type]

    def list_quality_failures(self, chapter_id: str) -> list[QualityFailure]:
        rows = self._conn.execute(
            "SELECT * FROM quality_failures WHERE chapter_id = ? "
            "ORDER BY created_at, id",
            (chapter_id,),
        ).fetchall()
        return [QualityFailure.from_row(row) for row in rows]

    def add_confirmation(
        self,
        chapter_id: str,
        gate_type: str,
        decision: str,
        *,
        confirmation_id: str | None = None,
    ) -> Confirmation:
        cid = confirmation_id or str(uuid.uuid4())
        with self._conn:
            self._conn.execute(
                "INSERT INTO confirmations "
                "(id, chapter_id, gate_type, decision) VALUES (?, ?, ?, ?)",
                (cid, chapter_id, gate_type, decision),
            )
        row = self._conn.execute(
            "SELECT * FROM confirmations WHERE id = ?", (cid,)
        ).fetchone()
        return Confirmation.from_row(row)  # type: ignore[arg-type]
