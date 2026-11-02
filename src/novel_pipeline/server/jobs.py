"""In-process generation jobs.

Local use is single-user and SQLite-backed, so an in-memory job table is
enough: the prose itself is persisted by ``ChapterPipeline``; a job only
tracks progress and the last result. The executor is deliberately serial by
default because concurrent writers to one SQLite file gain nothing and can
turn a long generation into a database-lock retry.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ..pipeline import GenerationRequest, PipelineResult


class ProjectBusyError(RuntimeError):
    """Raised when the same project already has a running generation."""


Runner = Callable[[GenerationRequest, str], PipelineResult]
TrialRunner = Callable[[GenerationRequest], dict]
Work = Callable[[], PipelineResult | dict]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class Job:
    id: str
    project_id: str
    chapter_seq: int
    quality_mode: str
    kind: str = "generate"  # generate | trial
    status: str = "queued"  # queued | running | done | failed
    message: str = "排队中"
    progress: int = 5
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    result: dict | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "chapter_seq": self.chapter_seq,
            "kind": self.kind,
            "quality_mode": self.quality_mode,
            "status": self.status,
            "message": self.message,
            "progress": self.progress,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "result": self.result,
            "error": self.error,
        }


class JobManager:
    MAX_FINISHED_JOBS = 100

    def __init__(
        self,
        runner: Runner,
        *,
        trial_runner: TrialRunner | None = None,
        max_workers: int = 1,
    ) -> None:
        self.runner = runner
        self.trial_runner = trial_runner
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="novel-job"
        )
        self._lock = threading.RLock()
        self._jobs: dict[str, Job] = {}
        self._active_projects: set[str] = set()

    def submit(
        self,
        request: GenerationRequest,
        quality_mode: str,
    ) -> Job:
        job = Job(
            id=str(uuid.uuid4()),
            project_id=request.project_id,
            chapter_seq=request.chapter_seq,
            quality_mode=quality_mode,
        )
        return self._start(
            job, lambda: self.runner(request, quality_mode)
        )

    def submit_trial(self, request: GenerationRequest) -> Job:
        if self.trial_runner is None:
            raise RuntimeError("试写功能未启用")
        job = Job(
            id=str(uuid.uuid4()),
            project_id=request.project_id,
            chapter_seq=request.chapter_seq,
            quality_mode="trial",
            kind="trial",
        )
        return self._start(job, lambda: self.trial_runner(request))

    def _start(self, job: Job, work: Work) -> Job:
        with self._lock:
            if job.project_id in self._active_projects:
                raise ProjectBusyError(
                    "这个作品已有一章正在生成，请等它结束再提交。"
                )
            self._active_projects.add(job.project_id)
            self._jobs[job.id] = job
            self._trim_finished()
        try:
            self._executor.submit(self._run, job, work)
        except Exception:
            with self._lock:
                self._active_projects.discard(job.project_id)
                self._jobs.pop(job.id, None)
            raise
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _run(self, job: Job, work: Work) -> None:
        self._update(
            job,
            status="running",
            message="正在写作并跑质量门" if job.kind == "generate" else "正在试写",
            progress=20,
        )
        try:
            result = work()
            if job.kind == "trial":
                self._update(
                    job,
                    status="done",
                    message="试写完成",
                    progress=100,
                    result=result,
                )
                return
            assert isinstance(result, PipelineResult)
            payload = result.to_dict()
            if result.status == "failed":
                self._update(
                    job,
                    status="failed",
                    message="生成失败",
                    progress=100,
                    result=payload,
                    error=result.error or "管线返回失败",
                )
            elif result.status == "final":
                self._update(
                    job,
                    status="done",
                    message="已定稿",
                    progress=100,
                    result=payload,
                )
            else:
                self._update(
                    job,
                    status="done",
                    message="待确认",
                    progress=100,
                    result=payload,
                )
        except Exception as exc:  # noqa: BLE001 - report failure to the UI
            self._update(
                job,
                status="failed",
                message="生成失败" if job.kind == "generate" else "试写失败",
                progress=100,
                error=str(exc),
            )
        finally:
            with self._lock:
                self._active_projects.discard(job.project_id)

    def _update(self, job: Job, **changes) -> None:
        with self._lock:
            for key, value in changes.items():
                setattr(job, key, value)
            job.updated_at = _now()

    def _trim_finished(self) -> None:
        finished = [
            item
            for item in self._jobs.values()
            if item.status in ("done", "failed")
        ]
        excess = len(finished) - self.MAX_FINISHED_JOBS
        if excess <= 0:
            return
        finished.sort(key=lambda item: item.updated_at)
        for item in finished[:excess]:
            self._jobs.pop(item.id, None)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)
