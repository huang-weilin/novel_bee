from pathlib import Path

from novel_pipeline.memory import MemoryStore
from novel_pipeline.memory.admin import main


def make_db(path: Path) -> tuple[str, str]:
    with MemoryStore(str(path)) as store:
        store.migrate()
        project = store.create_project("长夜", "仙侠")
        store.create_foreshadowing(
            project.id,
            "青铜钥匙",
            1,
            importance=3,
            target_chapter=6,
        )
        store.create_foreshadowing(
            project.id,
            "断裂的玉佩",
            2,
            importance=2,
            target_chapter=6,
        )
        store.create_emotional_thread(
            project.id,
            "半张图的人情",
            "沈砚",
            "老周",
            1,
            kind="rescue",
            target_payoff_chapter=12,
        )
        store.create_emotional_thread(
            project.id,
            "阿棠的误会",
            "沈砚",
            "阿棠",
            2,
            kind="apology",
            target_payoff_chapter=10,
        )
        store.upsert_ledger_item(project.id, "金疮药", quantity=2, unit="瓶")
        return project.id, project.title


def run(db: Path, *args: str) -> int:
    return main(["--db", str(db), *args])


def test_admin_lists_and_closes_foreshadowing(
    tmp_path: Path, capsys
) -> None:
    db = tmp_path / "memory.db"
    project_id, _ = make_db(db)

    assert run(db, "--project", "长夜", "foreshadow", "list") == 0
    output = capsys.readouterr().out
    assert "青铜钥匙" in output
    assert project_id in output

    assert (
        run(
            db,
            "--project",
            "长夜",
            "foreshadow",
            "close",
            "青铜钥匙",
            "--chapter",
            "5",
        )
        == 0
    )
    with MemoryStore(str(db)) as store:
        item = store.find_foreshadowing(project_id, "青铜钥匙")[0]
        assert item.status == "resolved"
        assert item.resolved_chapter == 5


def test_admin_reschedules_foreshadowing_and_threads(
    tmp_path: Path,
) -> None:
    db = tmp_path / "memory.db"
    project_id, _ = make_db(db)

    assert (
        run(
            db,
            "--project",
            project_id,
            "foreshadow",
            "reschedule",
            "断裂的玉佩",
            "--target",
            "9",
        )
        == 0
    )
    assert (
        run(
            db,
            "--project",
            "长夜",
            "thread",
            "reschedule",
            "阿棠的误会",
            "--target",
            "15",
        )
        == 0
    )
    assert (
        run(
            db,
            "--project",
            "长夜",
            "thread",
            "close",
            "半张图的人情",
        )
        == 0
    )

    with MemoryStore(str(db)) as store:
        item = store.find_foreshadowing(project_id, "断裂的玉佩")[0]
        assert item.target_chapter == 9
        thread = store.find_emotional_thread(project_id, "阿棠的误会")
        assert thread is not None
        assert thread.target_payoff_chapter == 15
        paid = store.find_emotional_thread(project_id, "半张图的人情")
        assert paid is not None
        assert paid.status == "paid"


def test_admin_manages_item_aliases(tmp_path: Path, capsys) -> None:
    db = tmp_path / "memory.db"
    project_id, _ = make_db(db)

    assert (
        run(
            db,
            "--project",
            "长夜",
            "alias",
            "set",
            "青布小包",
            "金疮药",
        )
        == 0
    )
    assert run(db, "--project", "长夜", "alias", "list") == 0
    assert "青布小包 -> 金疮药" in capsys.readouterr().out

    with MemoryStore(str(db)) as store:
        assert store.resolve_item_name(project_id, "青布小包") == "金疮药"

    assert (
        run(db, "--project", "长夜", "alias", "delete", "青布小包") == 0
    )
    with MemoryStore(str(db)) as store:
        assert store.get_item_alias(project_id, "青布小包") is None


def test_admin_reports_errors_without_traceback(
    tmp_path: Path, capsys
) -> None:
    db = tmp_path / "memory.db"
    make_db(db)

    assert run(db, "--project", "不存在", "foreshadow", "list") == 2
    assert "project not found" in capsys.readouterr().err

    assert (
        run(
            db,
            "--project",
            "长夜",
            "foreshadow",
            "reschedule",
            "青铜钥匙",
            "--target",
            "8",
        )
        == 0
    )
    assert (
        run(
            db,
            "--project",
            "长夜",
            "alias",
            "set",
            "青布小包",
            "不存在",
        )
        == 2
    )
    assert "ledger item not found" in capsys.readouterr().err
