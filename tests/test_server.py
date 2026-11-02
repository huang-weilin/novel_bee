from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import novel_pipeline.server.app as app_module
from novel_pipeline.config import ConfigError
from novel_pipeline.memory import MemoryStore
from novel_pipeline.pipeline import PipelineResult
from novel_pipeline.planning import SCENE_FIELD_LABELS
from novel_pipeline.quality.models import (
    ChapterInput,
    Decision,
    QualityReport,
    RuleFinding,
    Severity,
)
from novel_pipeline.server.app import create_app
from novel_pipeline.server.schemas import (
    ChapterGenerateRequest,
    ScenePlanIn,
)


def _fake_result(request, *, content: str, status: str = "pending"):
    quality = QualityReport(
        passed=status == "final",
        decision=Decision.ACCEPT if status == "final" else Decision.POLISH,
        score=82,
        failures=(
            []
            if status == "final"
            else [
                RuleFinding(
                    rule_id="Q08",
                    severity=Severity.MAJOR,
                    evidence="他明白了成长的意义。",
                    suggestion="用动作收尾。",
                )
            ]
        ),
    )
    return PipelineResult(
        request=request,
        chapter=ChapterInput(content=content),
        status=status,
        quality=quality,
    )


def _runner(db: Path, *, status: str = "pending"):
    def run(request, quality_mode):
        content = f"第{request.chapter_seq}章正文。"
        with MemoryStore(db) as store:
            store.upsert_chapter(
                request.project_id,
                request.chapter_seq,
                status,
                title=request.title or f"第{request.chapter_seq}章",
                content=content,
                score=82,
            )
        return _fake_result(request, content=content, status=status)

    return run


def _trial_runner(request):
    content = f"第{request.chapter_seq}章试写片段。"
    return {
        "status": "trial",
        "project_id": request.project_id,
        "chapter_seq": request.chapter_seq,
        "content": content,
        "chars": len(content),
        "target_words": request.target_words,
        "context_tokens": 12,
    }


def _make_app(tmp_path: Path, **kwargs):
    db = tmp_path / "novel.db"
    runner = kwargs.pop("runner", None) or _runner(db)
    trial_runner = kwargs.pop("trial_runner", None) or _trial_runner
    return create_app(
        data_path=db,
        runner=runner,
        trial_runner=trial_runner,
        require_llm=False,
        env_path=tmp_path / ".env",
        **kwargs,
    )


def _wait_job(client: TestClient, job_id: str, timeout: float = 3.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = client.get(f"/api/jobs/{job_id}").json()
        if payload["status"] in ("done", "failed"):
            return payload
        time.sleep(0.02)
    raise AssertionError(f"job did not finish: {payload}")


@pytest.fixture
def client(tmp_path: Path):
    app = _make_app(tmp_path)
    with TestClient(app) as test_client:
        yield test_client


def test_health_and_static_page(client: TestClient) -> None:
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert "llm" in health.json()

    page = client.get("/")
    assert page.status_code == 200
    assert "长篇小说工坊" in page.text
    assert "内容由 AI 生成" in page.text
    assert "AI 设置" in page.text
    assert 'id="settings-dialog"' in page.text
    assert 'id="setup-card"' in page.text


def test_genres_expose_scene_fields(client: TestClient) -> None:
    response = client.get("/api/genres")
    assert response.status_code == 200
    genres = {item["key"]: item for item in response.json()["genres"]}
    assert "xianxia_comedy" in genres
    assert "opening_hook" in genres["xianxia_comedy"]["required_fields"]
    field_names = {
        field["name"] for field in genres["xianxia_comedy"]["scene_fields"]
    }
    assert field_names == set(SCENE_FIELD_LABELS)


def test_scene_plan_schema_matches_planner_fields() -> None:
    assert set(ScenePlanIn.model_fields) == set(SCENE_FIELD_LABELS)


def test_generate_schema_passes_confirmed_trial_text() -> None:
    payload = ChapterGenerateRequest(
        outline="一章", trial_text="  雨声压低了脚步。  "
    )
    request = payload.to_generation_request("project", 2)
    assert request.trial_text == "雨声压低了脚步。"
    assert request.project_id == "project"
    assert request.chapter_seq == 2


def test_project_create_list_and_detail(client: TestClient) -> None:
    created = client.post(
        "/api/projects",
        json={"title": "测试书", "genre": "xianxia_comedy", "target_chapters": 12},
    )
    assert created.status_code == 201
    project = created.json()
    assert project["title"] == "测试书"
    assert project["genre_label"] == "仙侠喜剧"
    assert project["next_chapter_seq"] == 1

    listed = client.get("/api/projects").json()["projects"]
    assert len(listed) == 1
    assert listed[0]["id"] == project["id"]

    detail = client.get(f"/api/projects/{project['id']}")
    assert detail.status_code == 200
    assert detail.json()["profile"]["key"] == "xianxia_comedy"


def test_generate_job_persists_chapter_and_result(client: TestClient) -> None:
    project = client.post(
        "/api/projects", json={"title": "测试书", "genre": "default"}
    ).json()
    response = client.post(
        f"/api/projects/{project['id']}/chapters/generate",
        json={
            "outline": "主角去退押金，被前台刁难。",
            "target_words": 1500,
            "quality_mode": "rules",
            "scene_plan": {"payoff": "前台退回押金"},
        },
    )
    assert response.status_code == 202
    job = response.json()
    assert job["chapter_seq"] == 1
    assert job["status"] in ("queued", "running", "done")

    done = _wait_job(client, job["id"])
    assert done["status"] == "done"
    assert done["result"]["status"] == "pending"
    assert done["result"]["quality"]["failures"][0]["rule_id"] == "Q08"

    chapter = client.get(f"/api/projects/{project['id']}/chapters/1")
    assert chapter.status_code == 200
    assert "第1章正文" in chapter.json()["content"]

    detail = client.get(f"/api/projects/{project['id']}").json()
    assert detail["chapter_count"] == 1
    assert detail["pending_count"] == 1
    assert detail["next_chapter_seq"] == 2


def test_job_events_stream_terminal_state(client: TestClient) -> None:
    project = client.post(
        "/api/projects", json={"title": "流式测试", "genre": "default"}
    ).json()
    job = client.post(
        f"/api/projects/{project['id']}/chapters/generate",
        json={"outline": "主角去退押金。", "target_words": 1000},
    ).json()
    _wait_job(client, job["id"])

    response = client.get(f"/api/jobs/{job['id']}/events")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"

    payloads = []
    for block in response.text.split("\n\n"):
        if block.startswith("data: "):
            payloads.append(json.loads(block[len("data: ") :]))
    assert payloads, response.text
    assert payloads[-1]["id"] == job["id"]
    assert payloads[-1]["status"] == "done"
    assert payloads[-1]["result"]["status"] == "pending"
    assert "event: end" in response.text


def test_trial_returns_sample_without_writing_chapter(
    client: TestClient,
) -> None:
    project = client.post(
        "/api/projects", json={"title": "测试书", "genre": "default"}
    ).json()
    response = client.post(
        f"/api/projects/{project['id']}/chapters/trial",
        json={
            "outline": "主角去退押金，被前台刁难。",
            "target_words": 500,
        },
    )
    assert response.status_code == 202
    job = response.json()
    assert job["kind"] == "trial"
    done = _wait_job(client, job["id"])
    assert done["status"] == "done"
    assert done["message"] == "试写完成"
    assert done["result"]["status"] == "trial"
    assert "试写片段" in done["result"]["content"]

    project_after = client.get(f"/api/projects/{project['id']}").json()
    assert project_after["chapter_count"] == 0
    assert client.get(
        f"/api/projects/{project['id']}/chapters"
    ).json()["chapters"] == []


def test_trial_validation_and_final_chapter_guard(
    client: TestClient, tmp_path: Path
) -> None:
    project = client.post(
        "/api/projects", json={"title": "测试书", "genre": "default"}
    ).json()

    too_long = client.post(
        f"/api/projects/{project['id']}/chapters/trial",
        json={"outline": "一章", "target_words": 2000},
    )
    assert too_long.status_code == 422

    with MemoryStore(tmp_path / "novel.db") as store:
        store.upsert_chapter(project["id"], 1, "final", content="定稿")
    blocked = client.post(
        f"/api/projects/{project['id']}/chapters/trial",
        json={"outline": "一章", "chapter_seq": 1},
    )
    assert blocked.status_code == 409


def test_second_generation_uses_next_sequence(client: TestClient) -> None:
    project = client.post(
        "/api/projects", json={"title": "测试书", "genre": "default"}
    ).json()
    for _ in range(2):
        job = client.post(
            f"/api/projects/{project['id']}/chapters/generate",
            json={"outline": "一章"},
        ).json()
        _wait_job(client, job["id"])
    detail = client.get(f"/api/projects/{project['id']}").json()
    assert [item["seq"] for item in detail["chapters"]] == [1, 2]


def test_export_contains_written_chapter(client: TestClient) -> None:
    project = client.post(
        "/api/projects", json={"title": "测试书", "genre": "default"}
    ).json()
    job = client.post(
        f"/api/projects/{project['id']}/chapters/generate",
        json={"outline": "一章", "title": "押金"},
    ).json()
    _wait_job(client, job["id"])

    export = client.get(f"/api/projects/{project['id']}/export")
    assert export.status_code == 200
    assert "《测试书》" in export.text
    assert "押金" in export.text
    assert "第1章正文" in export.text
    assert "attachment" in export.headers["content-disposition"]


def test_rewrite_rejects_final_chapter(client: TestClient, tmp_path: Path) -> None:
    project = client.post(
        "/api/projects", json={"title": "测试书", "genre": "default"}
    ).json()
    with MemoryStore(tmp_path / "novel.db") as store:
        store.upsert_chapter(project["id"], 1, "final", content="定稿正文")

    response = client.post(
        f"/api/projects/{project['id']}/chapters/generate",
        json={"outline": "重写", "chapter_seq": 1},
    )
    assert response.status_code == 409


def test_validation_and_missing_project(client: TestClient) -> None:
    project = client.post(
        "/api/projects", json={"title": "测试书", "genre": "default"}
    ).json()
    blank = client.post(
        f"/api/projects/{project['id']}/chapters/generate",
        json={"outline": "   "},
    )
    assert blank.status_code == 422

    missing = client.post(
        "/api/projects/not-there/chapters/generate",
        json={"outline": "一章"},
    )
    assert missing.status_code == 404
    assert client.get("/api/projects/not-there").status_code == 404
    assert client.get("/api/jobs/not-there").status_code == 404
    assert client.get("/api/jobs/not-there/events").status_code == 404


def test_memory_endpoint_counts(client: TestClient) -> None:
    project = client.post(
        "/api/projects", json={"title": "测试书", "genre": "default"}
    ).json()
    with MemoryStore(Path(client.app.state.data_path)) as store:
        store.upsert_character(project["id"], "许青", status="调解员")
        store.create_foreshadowing(
            project["id"], "旧工牌", planted_chapter=1, target_chapter=8
        )

    memory = client.get(f"/api/projects/{project['id']}/memory")
    assert memory.status_code == 200
    payload = memory.json()
    assert payload["counts"]["characters"] == 1
    assert payload["counts"]["open_foreshadowing"] == 1
    assert payload["open_foreshadowing"][0]["title"] == "旧工牌"


def test_chapter_detail_exposes_review_items(
    client: TestClient, tmp_path: Path
) -> None:
    project = client.post(
        "/api/projects", json={"title": "测试书", "genre": "default"}
    ).json()
    items = [
        {
            "kind": "character",
            "name": "马师兄",
            "reason": "unknown_character",
            "detail": {"status": "外门弟子"},
        }
    ]
    with MemoryStore(tmp_path / "novel.db") as store:
        store.upsert_chapter(project["id"], 1, "pending", content="正文")
        store.set_chapter_review(project["id"], 1, items)

    detail = client.get(f"/api/projects/{project['id']}/chapters/1")
    assert detail.status_code == 200
    assert detail.json()["review_items"] == items


def test_register_character_and_item(client: TestClient) -> None:
    project = client.post(
        "/api/projects", json={"title": "测试书", "genre": "default"}
    ).json()

    character = client.post(
        f"/api/projects/{project['id']}/characters",
        json={
            "name": "马师兄",
            "status": "外门弟子",
            "core_attributes": {"身份": "外门弟子"},
            "first_chapter": 2,
        },
    )
    assert character.status_code == 201
    assert character.json()["name"] == "马师兄"
    assert character.json()["first_chapter"] == 2
    assert character.json()["last_chapter"] == 2

    updated = client.post(
        f"/api/projects/{project['id']}/characters",
        json={"name": "马师兄", "status": "外门执事"},
    )
    assert updated.status_code == 201
    assert updated.json()["status"] == "外门执事"

    item = client.post(
        f"/api/projects/{project['id']}/items",
        json={
            "name": "投诉台账",
            "quantity": 1,
            "unit": "本",
            "updated_chapter": 3,
        },
    )
    assert item.status_code == 201
    assert item.json()["quantity"] == 1
    assert item.json()["unit"] == "本"

    memory = client.get(f"/api/projects/{project['id']}/memory").json()
    assert memory["counts"]["characters"] == 1
    assert memory["counts"]["ledger_items"] == 1
    assert memory["characters"][0]["status"] == "外门执事"
    assert memory["ledger_items"][0]["name"] == "投诉台账"


def test_registration_validation_and_missing_project(
    client: TestClient,
) -> None:
    project = client.post(
        "/api/projects", json={"title": "测试书", "genre": "default"}
    ).json()

    blank_name = client.post(
        f"/api/projects/{project['id']}/characters",
        json={"name": "   "},
    )
    assert blank_name.status_code == 422

    negative = client.post(
        f"/api/projects/{project['id']}/items",
        json={"name": "投诉台账", "quantity": -1},
    )
    assert negative.status_code == 422

    assert (
        client.post(
            "/api/projects/not-there/characters", json={"name": "某人"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/projects/not-there/items", json={"name": "某物"}
        ).status_code
        == 404
    )


def test_pending_review_resolved_by_registration(tmp_path: Path) -> None:
    db = tmp_path / "novel.db"

    def runner(request, quality_mode):
        content = f"第{request.chapter_seq}章正文。"
        with MemoryStore(db) as store:
            resolved = (
                store.get_character(request.project_id, "马师兄") is not None
                and store.get_ledger_item(request.project_id, "投诉台账")
                is not None
            )
            status = "final" if resolved else "pending"
            store.upsert_chapter(
                request.project_id,
                request.chapter_seq,
                status,
                content=content,
                score=82,
            )
            if not resolved:
                store.set_chapter_review(
                    request.project_id,
                    request.chapter_seq,
                    [
                        {
                            "kind": "character",
                            "name": "马师兄",
                            "reason": "unknown_character",
                            "detail": {},
                        },
                        {
                            "kind": "item",
                            "name": "投诉台账",
                            "reason": "unknown_item",
                            "detail": {"delta": 1},
                        },
                    ],
                )
        return _fake_result(request, content=content, status=status)

    app = create_app(data_path=db, runner=runner, require_llm=False)
    with TestClient(app) as client:
        project = client.post(
            "/api/projects", json={"title": "测试书", "genre": "default"}
        ).json()
        first = client.post(
            f"/api/projects/{project['id']}/chapters/generate",
            json={"outline": "马师兄拿来一本投诉台账。"},
        ).json()
        done = _wait_job(client, first["id"])
        assert done["result"]["status"] == "pending"

        detail = client.get(
            f"/api/projects/{project['id']}/chapters/1"
        ).json()
        assert [item["name"] for item in detail["review_items"]] == [
            "马师兄",
            "投诉台账",
        ]

        for path, payload in (
            (
                "characters",
                {"name": "马师兄", "status": "外门弟子", "first_chapter": 1},
            ),
            ("items", {"name": "投诉台账", "quantity": 0, "unit": "本"}),
        ):
            response = client.post(
                f"/api/projects/{project['id']}/{path}", json=payload
            )
            assert response.status_code == 201

        second = client.post(
            f"/api/projects/{project['id']}/chapters/generate",
            json={"outline": "马师兄拿来一本投诉台账。", "chapter_seq": 1},
        ).json()
        retried = _wait_job(client, second["id"])
        assert retried["result"]["status"] == "final"

        detail = client.get(
            f"/api/projects/{project['id']}/chapters/1"
        ).json()
        assert detail["status"] == "final"
        assert detail["review_items"] == []


def test_busy_project_returns_409(tmp_path: Path) -> None:
    db = tmp_path / "novel.db"
    gate = threading.Event()

    def slow_runner(request, quality_mode):
        gate.wait(timeout=2)
        with MemoryStore(db) as store:
            store.upsert_chapter(
                request.project_id,
                request.chapter_seq,
                "pending",
                content="正文",
            )
        return _fake_result(request, content="正文")

    app = create_app(
        data_path=db, runner=slow_runner, require_llm=False, max_workers=1
    )
    with TestClient(app) as client:
        project = client.post(
            "/api/projects", json={"title": "测试书", "genre": "default"}
        ).json()
        first = client.post(
            f"/api/projects/{project['id']}/chapters/generate",
            json={"outline": "一章"},
        )
        assert first.status_code == 202
        second = client.post(
            f"/api/projects/{project['id']}/chapters/generate",
            json={"outline": "二章"},
        )
        assert second.status_code == 409
        gate.set()
        _wait_job(client, first.json()["id"])


def test_generate_requires_llm_when_enabled(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "novel.db"

    class BrokenConfig:
        @classmethod
        def from_env(cls):
            raise ConfigError("missing NOVEL_LLM_API_KEY")

    monkeypatch.setattr(app_module, "LLMConfig", BrokenConfig)
    app = create_app(data_path=db, runner=_runner(db), require_llm=True)
    with TestClient(app) as client:
        project = client.post(
            "/api/projects", json={"title": "测试书", "genre": "default"}
        ).json()
        response = client.post(
            f"/api/projects/{project['id']}/chapters/generate",
            json={"outline": "一章"},
        )
    assert response.status_code == 400
    assert "AI 接口未配置" in response.json()["detail"]
