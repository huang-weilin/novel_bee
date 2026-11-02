"""HTTP request models for the local web app and future mini-program.

The API is intentionally small and stable: a project owns chapters, a chapter
generation is queued as a job, and the browser polls the job. The WeChat
mini-program can use the same endpoints once its own login/confirmation layer
is added.
"""

from __future__ import annotations

from dataclasses import replace

from pydantic import BaseModel, Field, field_validator

from ..pipeline import GenerationRequest
from ..planning import ScenePlan

QUALITY_MODES = ("rules", "rules+llm", "rules+score", "full")


def _clean_text(value: str) -> str:
    return value.strip()


class LLMSettingsUpdate(BaseModel):
    """Values from the local AI settings dialog.

    ``api_key`` intentionally has no Pydantic length/format constraints: a
    validation error would echo the submitted secret. Detailed checks live in
    ``server/settings.py`` and use generic messages.
    """

    provider: str = Field(default="", max_length=80)
    model: str = Field(default="", max_length=200)
    base_url: str = Field(default="", max_length=500)
    api_key: str = ""


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    genre: str = Field(default="default", max_length=80)
    target_chapters: int | None = Field(default=None, ge=1, le=5000)

    @field_validator("title", "genre")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned


class CharacterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    status: str | None = Field(default=None, max_length=200)
    core_attributes: dict[str, str] = Field(default_factory=dict)
    first_chapter: int | None = Field(default=None, ge=1)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("status")
    @classmethod
    def _strip_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    quantity: float = Field(default=1, ge=0, le=1_000_000)
    unit: str = Field(default="件", max_length=20)
    updated_chapter: int | None = Field(default=None, ge=1)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("unit")
    @classmethod
    def _unit_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned


class ScenePlanIn(BaseModel):
    goal: str = Field(default="", max_length=4000)
    obstacle: str = Field(default="", max_length=4000)
    stakes: str = Field(default="", max_length=4000)
    emotional_target: str = Field(default="", max_length=4000)
    setup: str = Field(default="", max_length=4000)
    turn: str = Field(default="", max_length=4000)
    release: str = Field(default="", max_length=4000)
    aftertaste: str = Field(default="", max_length=4000)
    debt_paid: str = Field(default="", max_length=4000)
    debt_opened: str = Field(default="", max_length=4000)
    witnesses: str = Field(default="", max_length=4000)
    opening_hook: str = Field(default="", max_length=4000)
    reader_promise: str = Field(default="", max_length=4000)
    suppression: str = Field(default="", max_length=4000)
    payoff_tool: str = Field(default="", max_length=4000)
    payoff: str = Field(default="", max_length=4000)
    payoff_type: str = Field(default="", max_length=4000)
    bystander_reaction: str = Field(default="", max_length=4000)
    next_hook: str = Field(default="", max_length=4000)

    def to_plan(self) -> ScenePlan:
        return ScenePlan(**self.model_dump())


class ChapterTrialRequest(BaseModel):
    """A short, read-only sample used by the mini-program trial gate."""

    outline: str = Field(min_length=1, max_length=20_000)
    title: str | None = Field(default=None, max_length=120)
    chapter_seq: int | None = Field(default=None, ge=1)
    target_words: int = Field(default=500, ge=200, le=1200)
    pov: str = Field(default="第三人称", max_length=40)
    style_constraints: str = Field(default="", max_length=20_000)
    character_brief: str = Field(default="", max_length=10_000)
    scene_plan: ScenePlanIn = Field(default_factory=ScenePlanIn)

    @field_validator("outline")
    @classmethod
    def _outline_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("outline must not be blank")
        return cleaned

    @field_validator("pov", "style_constraints", "character_brief")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    def to_generation_request(
        self, project_id: str, chapter_seq: int
    ) -> GenerationRequest:
        return GenerationRequest(
            project_id=project_id,
            chapter_seq=chapter_seq,
            outline=self.outline,
            style_constraints=self.style_constraints,
            scene_plan=self.scene_plan.to_plan(),
            target_words=self.target_words,
            pov=self.pov,
            title=self.title,
            character_brief=self.character_brief,
        )


class ChapterGenerateRequest(ChapterTrialRequest):
    target_words: int = Field(default=2000, ge=200, le=20_000)
    trial_text: str = Field(default="", max_length=2000)
    quality_mode: str | None = None

    @field_validator("trial_text")
    @classmethod
    def _strip_trial(cls, value: str) -> str:
        return value.strip()

    @field_validator("quality_mode")
    @classmethod
    def _known_mode(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if cleaned not in QUALITY_MODES:
            raise ValueError(
                "quality_mode must be one of " + ", ".join(QUALITY_MODES)
            )
        return cleaned

    def to_generation_request(
        self, project_id: str, chapter_seq: int
    ) -> GenerationRequest:
        request = super().to_generation_request(project_id, chapter_seq)
        return replace(request, trial_text=self.trial_text)
