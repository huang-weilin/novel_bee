"""FastAPI application shared by the local web UI and future mini-program.

Two delivery paths use one backend:

- local: ``python -m novel_pipeline.server`` serves a static page and the API
  on loopback, so a GitHub download runs without a build step;
- WeChat mini-program: the same JSON endpoints, with login, confirmation
  screens and content-security checks added at the product layer.

Authentication is intentionally absent from the local loopback server. Do not
bind it to a public interface without adding an authenticated gateway.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..config import PROVIDERS, ConfigError, LLMConfig
from ..genre import all_profiles, resolve_genre
from ..llm import LLMClient
from ..memory import (
    Chapter,
    ContextAssembler,
    ContextBudget,
    EmotionalThread,
    Foreshadowing,
    MemoryStore,
    WorldRule,
)
from ..pipeline import (
    ChapterPipeline,
    GenerationRequest,
    PipelineResult,
    _clean_draft,
)
from ..planning import SCENE_FIELD_LABELS
from ..quality.adapter import QualityAdapter
from ..quality.scorer import LLMScorer
from ..quality.verifier import LLMVerifier
from .jobs import JobManager, ProjectBusyError, Runner, TrialRunner
from .schemas import (
    QUALITY_MODES,
    ChapterGenerateRequest,
    ChapterTrialRequest,
    CharacterCreate,
    ItemCreate,
    LLMSettingsUpdate,
    ProjectCreate,
)
from .settings import (
    SettingsError,
    read_settings,
    save_settings,
    test_connection,
)

_DEFAULT_DATA_PATH = "data/novel.db"
_DEFAULT_QUALITY_MODE = "full"
SSE_POLL_SECONDS = 0.5
SSE_KEEPALIVE_SECONDS = 10.0


def _project_payload(project, chapters: list[Chapter]) -> dict[str, Any]:
    profile = resolve_genre(project.genre)
    last = chapters[-1] if chapters else None
    return {
        "id": project.id,
        "title": project.title,
        "genre": project.genre,
        "genre_label": profile.label,
        "profile_key": profile.key,
        "target_chapters": project.target_chapters,
        "created_at": project.created_at,
        "chapter_count": len(chapters),
        "final_count": sum(1 for item in chapters if item.status == "final"),
        "pending_count": sum(1 for item in chapters if item.status == "pending"),
        "last_status": last.status if last else None,
        "last_score": last.score if last else None,
        "next_chapter_seq": (chapters[-1].seq + 1) if chapters else 1,
    }


def _chapter_row_payload(chapter: Chapter) -> dict[str, Any]:
    return {
        "id": chapter.id,
        "seq": chapter.seq,
        "status": chapter.status,
        "title": chapter.title,
        "summary": chapter.summary,
        "score": chapter.score,
        "rewrite_count": chapter.rewrite_count,
        "chars": len(chapter.content or ""),
        "created_at": chapter.created_at,
    }


def _chapter_detail_payload(chapter: Chapter) -> dict[str, Any]:
    payload = _chapter_row_payload(chapter)
    payload["project_id"] = chapter.project_id
    payload["content"] = chapter.content or ""
    payload["review_items"] = (
        json.loads(chapter.review_json) if chapter.review_json else []
    )
    return payload


def _foreshadowing_payload(item: Foreshadowing) -> dict[str, Any]:
    return {
        "id": item.id,
        "title": item.title,
        "planted_chapter": item.planted_chapter,
        "status": item.status,
        "importance": item.importance,
        "target_chapter": item.target_chapter,
        "last_touched_chapter": item.last_touched_chapter,
        "notes": item.notes,
    }


def _thread_payload(item: EmotionalThread) -> dict[str, Any]:
    return {
        "id": item.id,
        "title": item.title,
        "debt_from": item.debt_from,
        "debt_to": item.debt_to,
        "kind": item.kind,
        "status": item.status,
        "importance": item.importance,
        "setup_chapter": item.setup_chapter,
        "target_payoff_chapter": item.target_payoff_chapter,
        "last_touched_chapter": item.last_touched_chapter,
        "notes": item.notes,
    }


def _rule_payload(item: WorldRule) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "content": item.content,
        "importance": item.importance,
        "source_chapter": item.source_chapter,
        "updated_chapter": item.updated_chapter,
        "status": item.status,
    }


def _memory_payload(store: MemoryStore, project_id: str) -> dict[str, Any]:
    characters = store.list_characters(project_id)
    items = store.list_ledger_items(project_id)
    foreshadowing = store.list_foreshadowing(project_id, status="planted")
    threads = store.list_emotional_threads(project_id, status="open")
    rules = store.list_world_rules(project_id, status="active")
    return {
        "counts": {
            "characters": len(characters),
            "ledger_items": len(items),
            "open_foreshadowing": len(foreshadowing),
            "open_emotional_threads": len(threads),
            "active_world_rules": len(rules),
        },
        "open_foreshadowing": [
            _foreshadowing_payload(item) for item in foreshadowing[:10]
        ],
        "open_emotional_threads": [
            _thread_payload(item) for item in threads[:10]
        ],
        "active_world_rules": [_rule_payload(item) for item in rules[:10]],
        "characters": [
            {
                "name": item.name,
                "alive": item.alive,
                "status": item.status,
                "first_chapter": item.first_chapter,
                "last_chapter": item.last_chapter,
            }
            for item in characters[:20]
        ],
        "ledger_items": [
            {
                "name": item.name,
                "quantity": item.quantity,
                "unit": item.unit,
                "updated_chapter": item.updated_chapter,
            }
            for item in items[:20]
        ],
    }


def _build_runner(data_path: str | Path) -> Runner:
    def run(request: GenerationRequest, quality_mode: str) -> PipelineResult:
        with MemoryStore(data_path) as store:
            verifier = (
                LLMVerifier()
                if quality_mode in ("rules+llm", "full")
                else None
            )
            scorer = (
                LLMScorer()
                if quality_mode in ("rules+score", "full")
                else None
            )
            pipeline = ChapterPipeline(
                store,
                quality=QualityAdapter(verifier=verifier, scorer=scorer),
                quality_mode=quality_mode,
            )
            return pipeline.run(request)

    return run


TRIAL_SUFFIX = """【试写要求】
只写本章开头的一个试写片段，约 {target_words} 字（允许上下浮动两成），停在自然处。
不要写完整章，不要总结，不要解释；只输出正文。"""


def _build_trial_runner(data_path: str | Path) -> TrialRunner:
    """Write a short sample without quality checks or memory writes."""

    def run(request: GenerationRequest) -> dict[str, Any]:
        with MemoryStore(data_path) as store:
            context = ContextAssembler(store, ContextBudget()).build(
                request.project_id,
                request.chapter_seq,
                outline=request.outline,
                style_constraints=request.style_constraints,
                scene_plan=request.scene_plan,
                target_words=request.target_words,
                pov=request.pov,
            )
        prompt = (
            context.text
            + "\n\n"
            + TRIAL_SUFFIX.format(target_words=request.target_words)
        )
        client = LLMClient(LLMConfig.from_env())
        text = _clean_draft(
            client.complete(prompt, max_tokens=4096)
        )
        if not text:
            raise ValueError("试写返回了空正文")
        return {
            "status": "trial",
            "project_id": request.project_id,
            "chapter_seq": request.chapter_seq,
            "content": text,
            "chars": len(text),
            "target_words": request.target_words,
            "context_tokens": context.token_estimate,
        }

    return run


def _llm_status(env_path: str | Path = ".env") -> dict[str, Any]:
    settings = read_settings(env_path=env_path)
    provider = settings.get("provider") or ""
    profile = PROVIDERS.get(provider)
    return {
        "configured": bool(settings.get("key_configured"))
        and not settings.get("error"),
        "provider": provider,
        "model": settings.get("model") or "",
        "protocol": profile.protocol if profile else None,
        "base_url": settings.get("base_url") or "",
        "error": settings.get("error"),
    }


def _is_loopback_host(host_header: str | None) -> bool:
    """Accept only a local browser origin for settings changes."""
    if not host_header:
        return False
    host = host_header.strip().lower()
    if host.startswith("["):
        host = host[1:].split("]", 1)[0]
    elif host.count(":") == 1:
        host = host.rsplit(":", 1)[0]
    if host in ("localhost", "testserver"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _require_local_settings(request: Request) -> None:
    if not _is_loopback_host(request.headers.get("host")):
        raise HTTPException(
            status_code=403,
            detail=(
                "AI 设置只允许在本机打开网页时使用。"
                "请访问 http://127.0.0.1:8000，或直接编辑本机 .env 文件。"
            ),
        )


def create_app(
    *,
    data_path: str | Path = _DEFAULT_DATA_PATH,
    default_quality_mode: str = _DEFAULT_QUALITY_MODE,
    runner: Runner | None = None,
    trial_runner: TrialRunner | None = None,
    require_llm: bool = True,
    max_workers: int = 1,
    env_path: str | Path = ".env",
) -> FastAPI:
    """Build the HTTP app. Tests inject runners and disable the LLM check."""
    if default_quality_mode not in QUALITY_MODES:
        raise ValueError(
            f"default_quality_mode must be one of {', '.join(QUALITY_MODES)}"
        )
    path = Path(data_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    store_factory = lambda: MemoryStore(path)
    active_runner = runner or _build_runner(path)
    active_trial_runner = trial_runner or _build_trial_runner(path)
    manager = JobManager(
        active_runner,
        trial_runner=active_trial_runner,
        max_workers=max_workers,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        manager.shutdown()

    app = FastAPI(
        title="Novel Pipeline",
        version=__version__,
        description="长篇小说生成管线的本地 HTTP 接口",
        lifespan=lifespan,
    )
    app.state.data_path = str(path)
    app.state.default_quality_mode = default_quality_mode
    app.state.store_factory = store_factory
    app.state.jobs = manager
    app.state.require_llm = require_llm
    app.state.env_path = str(env_path)

    static_dir = Path(__file__).with_name("static")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.middleware("http")
    async def _headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/api/health")
    def health(request: Request) -> dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "data_path": request.app.state.data_path,
            "quality_mode": request.app.state.default_quality_mode,
            "llm": _llm_status(request.app.state.env_path),
        }

    @app.get("/api/settings")
    def get_settings(request: Request) -> dict[str, Any]:
        _require_local_settings(request)
        return read_settings(
            data_path=request.app.state.data_path,
            env_path=request.app.state.env_path,
        )

    @app.post("/api/settings")
    def update_settings(
        payload: LLMSettingsUpdate, request: Request
    ) -> dict[str, Any]:
        _require_local_settings(request)
        try:
            return save_settings(
                request.app.state.env_path,
                provider=payload.provider,
                model=payload.model,
                base_url=payload.base_url,
                api_key=payload.api_key,
                data_path=request.app.state.data_path,
            )
        except SettingsError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=500, detail=f"保存本机 .env 失败：{exc}"
            ) from exc

    @app.post("/api/settings/test")
    def test_settings(
        payload: LLMSettingsUpdate, request: Request
    ) -> dict[str, Any]:
        _require_local_settings(request)
        return test_connection(
            provider=payload.provider,
            model=payload.model,
            base_url=payload.base_url,
            api_key=payload.api_key,
            env_path=request.app.state.env_path,
        )

    @app.get("/api/genres")
    def genres() -> dict[str, Any]:
        items = []
        for profile in all_profiles():
            items.append(
                {
                    "key": profile.key,
                    "label": profile.label,
                    "aliases": list(profile.aliases),
                    "required_fields": list(profile.scene_plan_required),
                    "scene_fields": [
                        {
                            "name": name,
                            "label": label,
                            "required": name in profile.scene_plan_required,
                        }
                        for name, label in SCENE_FIELD_LABELS.items()
                    ],
                    "quality_notes": list(profile.quality_notes),
                }
            )
        return {"genres": items}

    @app.get("/api/projects")
    def list_projects() -> dict[str, Any]:
        with store_factory() as store:
            items = [
                _project_payload(project, store.list_chapters(project.id))
                for project in store.list_projects()
            ]
        return {"projects": items}

    @app.post("/api/projects", status_code=201)
    def create_project(payload: ProjectCreate) -> dict[str, Any]:
        with store_factory() as store:
            project = store.create_project(
                payload.title,
                payload.genre,
                payload.target_chapters,
            )
            chapters = store.list_chapters(project.id)
            return _project_payload(project, chapters)

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str) -> dict[str, Any]:
        with store_factory() as store:
            project = store.get_project(project_id)
            if project is None:
                raise HTTPException(status_code=404, detail="作品不存在")
            chapters = store.list_chapters(project_id)
            payload = _project_payload(project, chapters)
            profile = resolve_genre(project.genre)
            payload["profile"] = {
                "key": profile.key,
                "label": profile.label,
                "required_fields": list(profile.scene_plan_required),
            }
            payload["chapters"] = [
                _chapter_row_payload(chapter) for chapter in chapters
            ]
        return payload

    @app.get("/api/projects/{project_id}/memory")
    def get_memory(project_id: str) -> dict[str, Any]:
        with store_factory() as store:
            if store.get_project(project_id) is None:
                raise HTTPException(status_code=404, detail="作品不存在")
            return _memory_payload(store, project_id)

    @app.post("/api/projects/{project_id}/characters", status_code=201)
    def create_character(
        project_id: str, payload: CharacterCreate
    ) -> dict[str, Any]:
        with store_factory() as store:
            if store.get_project(project_id) is None:
                raise HTTPException(status_code=404, detail="作品不存在")
            character = store.upsert_character(
                project_id,
                payload.name,
                status=payload.status,
                core_attributes=payload.core_attributes,
                first_chapter=payload.first_chapter,
                last_chapter=payload.first_chapter,
            )
        return {
            "name": character.name,
            "alive": character.alive,
            "status": character.status,
            "core_attributes": character.core_attributes,
            "first_chapter": character.first_chapter,
            "last_chapter": character.last_chapter,
        }

    @app.post("/api/projects/{project_id}/items", status_code=201)
    def create_item(project_id: str, payload: ItemCreate) -> dict[str, Any]:
        with store_factory() as store:
            if store.get_project(project_id) is None:
                raise HTTPException(status_code=404, detail="作品不存在")
            item = store.upsert_ledger_item(
                project_id,
                payload.name,
                payload.quantity,
                unit=payload.unit,
                updated_chapter=payload.updated_chapter,
            )
        return {
            "name": item.name,
            "quantity": item.quantity,
            "unit": item.unit,
            "updated_chapter": item.updated_chapter,
        }

    @app.get("/api/projects/{project_id}/chapters")
    def list_chapters(project_id: str) -> dict[str, Any]:
        with store_factory() as store:
            if store.get_project(project_id) is None:
                raise HTTPException(status_code=404, detail="作品不存在")
            chapters = store.list_chapters(project_id)
        return {"chapters": [_chapter_row_payload(item) for item in chapters]}

    @app.get("/api/projects/{project_id}/chapters/{seq}")
    def get_chapter(project_id: str, seq: int) -> dict[str, Any]:
        with store_factory() as store:
            chapter = store.get_chapter(project_id, seq)
            if chapter is None:
                raise HTTPException(status_code=404, detail="章节不存在")
            return _chapter_detail_payload(chapter)

    @app.post("/api/projects/{project_id}/chapters/generate", status_code=202)
    def generate_chapter(
        project_id: str, payload: ChapterGenerateRequest, request: Request
    ) -> JSONResponse:
        with store_factory() as store:
            project = store.get_project(project_id)
            if project is None:
                raise HTTPException(status_code=404, detail="作品不存在")
            chapters = store.list_chapters(project_id)
            if payload.chapter_seq is None:
                chapter_seq = (chapters[-1].seq + 1) if chapters else 1
            else:
                chapter_seq = payload.chapter_seq
                existing = store.get_chapter(project_id, chapter_seq)
                if existing is None:
                    raise HTTPException(
                        status_code=404,
                        detail="要重写的章节不存在；新章节请不要传 chapter_seq",
                    )
                if existing.status != "pending":
                    raise HTTPException(
                        status_code=409,
                        detail="只有待确认章节可以重写；已定稿章节受记忆保护",
                    )

        if request.app.state.require_llm:
            try:
                LLMConfig.from_env()
            except ConfigError as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"AI 接口未配置：{exc}",
                ) from exc

        quality_mode = (
            payload.quality_mode
            or request.app.state.default_quality_mode
        )
        generation = payload.to_generation_request(project_id, chapter_seq)
        try:
            job = manager.submit(generation, quality_mode)
        except ProjectBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return JSONResponse(status_code=202, content=job.to_dict())

    @app.post(
        "/api/projects/{project_id}/chapters/trial", status_code=202
    )
    def trial_chapter(
        project_id: str, payload: ChapterTrialRequest, request: Request
    ) -> JSONResponse:
        with store_factory() as store:
            project = store.get_project(project_id)
            if project is None:
                raise HTTPException(status_code=404, detail="作品不存在")
            chapters = store.list_chapters(project_id)
            if payload.chapter_seq is None:
                chapter_seq = (chapters[-1].seq + 1) if chapters else 1
            else:
                chapter_seq = payload.chapter_seq
                existing = store.get_chapter(project_id, chapter_seq)
                if existing is None:
                    raise HTTPException(
                        status_code=404,
                        detail="要试写的章节不存在；新章节请不要传 chapter_seq",
                    )
                if existing.status != "pending":
                    raise HTTPException(
                        status_code=409,
                        detail="只有待确认章节可以重新试写；已定稿章节受记忆保护",
                    )

        if request.app.state.require_llm:
            try:
                LLMConfig.from_env()
            except ConfigError as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"AI 接口未配置：{exc}",
                ) from exc

        generation = payload.to_generation_request(project_id, chapter_seq)
        try:
            job = manager.submit_trial(generation)
        except ProjectBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(status_code=202, content=job.to_dict())

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        job = manager.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="任务不存在或已过期")
        return job.to_dict()

    @app.get("/api/jobs/{job_id}/events")
    async def job_events(job_id: str, request: Request) -> StreamingResponse:
        """Stream job state as Server-Sent Events.

        This streams *progress*, not model tokens: the worker is a blocking
        thread and the LLM client is non-streaming. The browser closes the
        EventSource as soon as it sees a terminal status. The mini-program
        keeps polling because WeChat has no EventSource.
        """
        if manager.get(job_id) is None:
            raise HTTPException(status_code=404, detail="任务不存在或已过期")

        async def events() -> Any:
            last_payload = ""
            idle_seconds = 0.0
            while True:
                if await request.is_disconnected():
                    return
                job = manager.get(job_id)
                if job is None:
                    return
                payload = json.dumps(job.to_dict(), ensure_ascii=False)
                if payload != last_payload:
                    last_payload = payload
                    idle_seconds = 0.0
                    yield f"data: {payload}\n\n"
                else:
                    idle_seconds += SSE_POLL_SECONDS
                    if idle_seconds >= SSE_KEEPALIVE_SECONDS:
                        idle_seconds = 0.0
                        yield ": keep-alive\n\n"
                if job.status in ("done", "failed"):
                    yield "event: end\ndata: {}\n\n"
                    return
                await asyncio.sleep(SSE_POLL_SECONDS)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/projects/{project_id}/export")
    def export_project(
        project_id: str,
        include_pending: bool = Query(default=True),
    ) -> Response:
        with store_factory() as store:
            project = store.get_project(project_id)
            if project is None:
                raise HTTPException(status_code=404, detail="作品不存在")
            chapters = store.list_chapters(project_id)
        selected = [
            item
            for item in chapters
            if item.content
            and (include_pending or item.status == "final")
        ]
        lines = [f"《{project.title}》", f"题材：{project.genre}", ""]
        for item in selected:
            title = item.title or f"第{item.seq}章"
            lines.append("=" * 24)
            lines.append(title)
            lines.append(f"状态：{item.status}")
            lines.append("")
            lines.append(item.content or "")
            lines.append("")
        body = "\n".join(lines).strip() + "\n"
        filename = f"novel-{project_id[:8]}.txt"
        return Response(
            content=body,
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{filename}"; '
                    f"filename*=UTF-8''{quote(filename)}"
                )
            },
        )

    return app


def run_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    data_path: str | Path = _DEFAULT_DATA_PATH,
    quality_mode: str = _DEFAULT_QUALITY_MODE,
) -> None:
    """Uvicorn entry used by ``python -m novel_pipeline.server``."""
    import uvicorn

    app = create_app(
        data_path=data_path,
        default_quality_mode=quality_mode,
    )
    uvicorn.run(app, host=host, port=port, log_level=os.getenv(
        "NOVEL_SERVER_LOG_LEVEL", "info"
    ))


__all__ = ["create_app", "run_server"]
