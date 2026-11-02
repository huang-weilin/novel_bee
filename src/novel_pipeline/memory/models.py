"""Typed rows for the structured memory store.

The SQLite adapter returns these dataclasses so downstream code does not
depend on ``sqlite3.Row`` or on a particular database driver.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass


def _loads(raw: str | None, default):
    if raw is None or raw == "":
        return default
    return json.loads(raw)


@dataclass(frozen=True)
class Project:
    id: str
    title: str
    genre: str
    target_chapters: int | None
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Project:
        return cls(
            id=row["id"],
            title=row["title"],
            genre=row["genre"],
            target_chapters=row["target_chapters"],
            created_at=row["created_at"],
        )


@dataclass(frozen=True)
class Chapter:
    id: str
    project_id: str
    seq: int
    status: str
    title: str | None
    content: str | None
    summary: str | None
    score: int | None
    rewrite_count: int
    created_at: str
    review_json: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Chapter:
        return cls(
            id=row["id"],
            project_id=row["project_id"],
            seq=row["seq"],
            status=row["status"],
            title=row["title"],
            content=row["content"],
            summary=row["summary"],
            score=row["score"],
            rewrite_count=row["rewrite_count"],
            created_at=row["created_at"],
            review_json=row["review_json"],
        )


@dataclass(frozen=True)
class Character:
    id: str
    project_id: str
    name: str
    alive: bool
    status: str | None
    core_attributes: dict
    first_chapter: int | None
    last_chapter: int | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Character:
        return cls(
            id=row["id"],
            project_id=row["project_id"],
            name=row["name"],
            alive=bool(row["alive"]),
            status=row["status"],
            core_attributes=_loads(row["core_attributes"], {}),
            first_chapter=row["first_chapter"],
            last_chapter=row["last_chapter"],
        )


@dataclass(frozen=True)
class CharacterEvent:
    id: str
    character_id: str
    chapter_seq: int
    event_summary: str
    story_time: str | None
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> CharacterEvent:
        return cls(
            id=row["id"],
            character_id=row["character_id"],
            chapter_seq=row["chapter_seq"],
            event_summary=row["event_summary"],
            story_time=row["story_time"],
            created_at=row["created_at"],
        )


@dataclass(frozen=True)
class LedgerItem:
    id: str
    project_id: str
    name: str
    quantity: float
    unit: str | None
    updated_chapter: int | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> LedgerItem:
        return cls(
            id=row["id"],
            project_id=row["project_id"],
            name=row["name"],
            quantity=row["quantity"],
            unit=row["unit"],
            updated_chapter=row["updated_chapter"],
        )


@dataclass(frozen=True)
class ItemAlias:
    project_id: str
    alias: str
    canonical_name: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> ItemAlias:
        return cls(
            project_id=row["project_id"],
            alias=row["alias"],
            canonical_name=row["canonical_name"],
        )


@dataclass(frozen=True)
class InfoGap:
    id: str
    project_id: str
    character_id: str
    known_facts: list
    unknown_facts: list
    updated_chapter: int | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> InfoGap:
        return cls(
            id=row["id"],
            project_id=row["project_id"],
            character_id=row["character_id"],
            known_facts=_loads(row["known_facts"], []),
            unknown_facts=_loads(row["unknown_facts"], []),
            updated_chapter=row["updated_chapter"],
        )


@dataclass(frozen=True)
class Foreshadowing:
    id: str
    project_id: str
    title: str
    planted_chapter: int
    resolved_chapter: int | None
    status: str
    notes: str | None
    importance: int = 1
    target_chapter: int | None = None
    last_touched_chapter: int | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Foreshadowing:
        return cls(
            id=row["id"],
            project_id=row["project_id"],
            title=row["title"],
            planted_chapter=row["planted_chapter"],
            resolved_chapter=row["resolved_chapter"],
            status=row["status"],
            notes=row["notes"],
            importance=row["importance"],
            target_chapter=row["target_chapter"],
            last_touched_chapter=row["last_touched_chapter"],
        )


@dataclass(frozen=True)
class EmotionalThread:
    id: str
    project_id: str
    title: str
    debt_from: str
    debt_to: str
    kind: str
    setup_chapter: int
    target_payoff_chapter: int | None
    status: str
    importance: int
    last_touched_chapter: int | None
    notes: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> EmotionalThread:
        return cls(
            id=row["id"],
            project_id=row["project_id"],
            title=row["title"],
            debt_from=row["debt_from"],
            debt_to=row["debt_to"],
            kind=row["kind"],
            setup_chapter=row["setup_chapter"],
            target_payoff_chapter=row["target_payoff_chapter"],
            status=row["status"],
            importance=row["importance"],
            last_touched_chapter=row["last_touched_chapter"],
            notes=row["notes"],
        )


@dataclass(frozen=True)
class WorldRule:
    id: str
    project_id: str
    name: str
    content: str
    importance: int
    source_chapter: int | None
    updated_chapter: int | None
    status: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> WorldRule:
        return cls(
            id=row["id"],
            project_id=row["project_id"],
            name=row["name"],
            content=row["content"],
            importance=row["importance"],
            source_chapter=row["source_chapter"],
            updated_chapter=row["updated_chapter"],
            status=row["status"],
        )


@dataclass(frozen=True)
class QualityFailure:
    id: str
    chapter_id: str
    layer: str
    rule_id: str
    severity: str
    evidence: str | None
    resolved: bool
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> QualityFailure:
        return cls(
            id=row["id"],
            chapter_id=row["chapter_id"],
            layer=row["layer"],
            rule_id=row["rule_id"],
            severity=row["severity"],
            evidence=row["evidence"],
            resolved=bool(row["resolved"]),
            created_at=row["created_at"],
        )


@dataclass(frozen=True)
class Confirmation:
    id: str
    chapter_id: str
    gate_type: str
    decision: str
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Confirmation:
        return cls(
            id=row["id"],
            chapter_id=row["chapter_id"],
            gate_type=row["gate_type"],
            decision=row["decision"],
            created_at=row["created_at"],
        )
