"""Local admin CLI for manual memory fixes.

Before the HTTP layer exists, editors still need a safe way to close or
reschedule foreshadowing and emotional threads, and to map an extractor's
alias to a real ledger item. This module uses public ``MemoryStore`` methods;
it never edits SQLite directly.

Examples::

    python -m novel_pipeline.memory.admin --db data/novel.db projects
    python -m novel_pipeline.memory.admin --db data/novel.db \
        --project 长夜 foreshadow list
    python -m novel_pipeline.memory.admin --db data/novel.db \
        --project 长夜 foreshadow close 青铜钥匙 --chapter 12
    python -m novel_pipeline.memory.admin --db data/novel.db \
        --project 长夜 alias set 青布小包 金疮药
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from .models import EmotionalThread, Foreshadowing, Project
from .store import MemoryStore


def _resolve_project(store: MemoryStore, ref: str) -> Project:
    project = store.get_project(ref)
    if project is not None:
        return project
    matches = [item for item in store.list_projects() if item.title == ref]
    if not matches:
        raise KeyError(f"project not found: {ref}")
    if len(matches) > 1:
        ids = ", ".join(item.id for item in matches)
        raise ValueError(f"project title is ambiguous: {ref} ({ids})")
    return matches[0]


def _find_foreshadowing(
    store: MemoryStore, project_id: str, key: str
) -> Foreshadowing:
    item = store.get_foreshadowing(key)
    if item is not None:
        if item.project_id != project_id:
            raise KeyError(f"foreshadowing belongs to another project: {key}")
        return item
    matches = store.find_foreshadowing(project_id, key)
    if not matches:
        raise KeyError(f"foreshadowing not found: {key}")
    if len(matches) > 1:
        ids = ", ".join(match.id for match in matches)
        raise ValueError(f"foreshadowing title is ambiguous: {key} ({ids})")
    return matches[0]


def _find_thread(
    store: MemoryStore, project_id: str, key: str
) -> EmotionalThread:
    item = store.get_emotional_thread(key)
    if item is not None:
        if item.project_id != project_id:
            raise KeyError(f"emotional thread belongs to another project: {key}")
        return item
    match = store.find_emotional_thread(project_id, key)
    if match is None:
        raise KeyError(f"emotional thread not found: {key}")
    return match


def _print_project(project: Project) -> None:
    print(f"项目：{project.title} ({project.id})")


def _print_foreshadowing(item: Foreshadowing) -> None:
    target = (
        f" 目标第{item.target_chapter}章" if item.target_chapter else ""
    )
    print(
        f"{item.id}  [{item.status}] 第{item.planted_chapter}章埋"
        f"{target} 重要度{item.importance}  {item.title}"
    )


def _print_thread(item: EmotionalThread) -> None:
    target = (
        f" 目标第{item.target_payoff_chapter}章"
        if item.target_payoff_chapter
        else ""
    )
    print(
        f"{item.id}  [{item.status}] 第{item.setup_chapter}章欠"
        f"{target} 重要度{item.importance}  {item.title}"
        f"（{item.debt_from} → {item.debt_to}）"
    )


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("必须是整数") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("必须 >= 1")
    return number


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m novel_pipeline.memory.admin",
        description="人工关闭/改期伏笔与情感债，维护物品别名。",
    )
    parser.add_argument("--db", required=True, help="SQLite 数据库路径")
    parser.add_argument(
        "--project",
        help="项目 ID 或书名；projects 命令不需要",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("projects", help="列出所有项目")

    foreshadow = commands.add_parser("foreshadow", help="伏笔管理")
    foreshadow_commands = foreshadow.add_subparsers(
        dest="foreshadow_command", required=True
    )
    foreshadow_list = foreshadow_commands.add_parser("list", help="列出伏笔")
    foreshadow_list.add_argument(
        "--status",
        choices=("planted", "resolved", "abandoned"),
        help="只看某个状态",
    )
    foreshadow_close = foreshadow_commands.add_parser(
        "close", help="关闭伏笔（默认 resolved）"
    )
    foreshadow_close.add_argument("key", help="伏笔 ID 或标题")
    foreshadow_close.add_argument(
        "--abandoned", action="store_true", help="标记为放弃，而不是回收"
    )
    foreshadow_close.add_argument(
        "--chapter", type=_positive_int, help="回收章节"
    )
    foreshadow_close.add_argument("--notes", help="备注")
    foreshadow_reschedule = foreshadow_commands.add_parser(
        "reschedule", help="修改目标章节"
    )
    foreshadow_reschedule.add_argument("key", help="伏笔 ID 或标题")
    foreshadow_reschedule.add_argument(
        "--target", type=_positive_int, required=True, help="新的目标章节"
    )
    foreshadow_reschedule.add_argument("--notes", help="备注")

    thread = commands.add_parser("thread", help="情感债管理")
    thread_commands = thread.add_subparsers(
        dest="thread_command", required=True
    )
    thread_list = thread_commands.add_parser("list", help="列出情感债")
    thread_list.add_argument(
        "--status",
        choices=("open", "paid", "abandoned"),
        help="只看某个状态",
    )
    thread_close = thread_commands.add_parser(
        "close", help="关闭情感债（默认 paid）"
    )
    thread_close.add_argument("key", help="情感债 ID 或标题")
    thread_close.add_argument(
        "--abandoned", action="store_true", help="标记为放弃，而不是还清"
    )
    thread_close.add_argument("--notes", help="备注")
    thread_reschedule = thread_commands.add_parser(
        "reschedule", help="修改目标偿还章节"
    )
    thread_reschedule.add_argument("key", help="情感债 ID 或标题")
    thread_reschedule.add_argument(
        "--target", type=_positive_int, required=True, help="新的目标章节"
    )
    thread_reschedule.add_argument("--notes", help="备注")

    alias = commands.add_parser("alias", help="物品别名管理")
    alias_commands = alias.add_subparsers(
        dest="alias_command", required=True
    )
    alias_commands.add_parser("list", help="列出别名")
    alias_set = alias_commands.add_parser("set", help="新增或更新别名")
    alias_set.add_argument("alias", help="抽取器写出的名字")
    alias_set.add_argument("canonical", help="账本里的标准名")
    alias_delete = alias_commands.add_parser("delete", help="删除别名")
    alias_delete.add_argument("alias", help="要删除的别名")

    return parser


def _require_project(parser: argparse.ArgumentParser, args) -> str:
    if not args.project:
        parser.error("此命令需要 --project")
    return args.project


def _run(parser: argparse.ArgumentParser, store: MemoryStore, args) -> int:
    if args.command == "projects":
        projects = store.list_projects()
        if not projects:
            print("（还没有项目）")
        for project in projects:
            print(f"{project.id}  {project.title}  {project.genre}")
        return 0

    project = _resolve_project(store, _require_project(parser, args))
    _print_project(project)

    if args.command == "foreshadow":
        if args.foreshadow_command == "list":
            items = store.list_foreshadowing(project.id, args.status)
            if not items:
                print("（没有伏笔）")
            for item in items:
                _print_foreshadowing(item)
            return 0
        item = _find_foreshadowing(store, project.id, args.key)
        if args.foreshadow_command == "close":
            status = "abandoned" if args.abandoned else "resolved"
            updated = store.update_foreshadowing(
                item.id,
                status=status,
                resolved_chapter=args.chapter,
                notes=args.notes,
            )
            print(f"已更新伏笔：{updated.title} -> {updated.status}")
            _print_foreshadowing(updated)
            return 0
        updated = store.update_foreshadowing(
            item.id,
            target_chapter=args.target,
            notes=args.notes,
        )
        print(f"已改期伏笔：{updated.title} -> 第{updated.target_chapter}章")
        return 0

    if args.command == "thread":
        if args.thread_command == "list":
            threads = store.list_emotional_threads(project.id, args.status)
            if not threads:
                print("（没有情感债）")
            for item in threads:
                _print_thread(item)
            return 0
        item = _find_thread(store, project.id, args.key)
        if args.thread_command == "close":
            status = "abandoned" if args.abandoned else "paid"
            updated = store.update_emotional_thread(
                item.id, status=status, notes=args.notes
            )
            print(f"已更新情感债：{updated.title} -> {updated.status}")
            _print_thread(updated)
            return 0
        updated = store.update_emotional_thread(
            item.id,
            target_payoff_chapter=args.target,
            notes=args.notes,
        )
        print(
            f"已改期情感债：{updated.title} -> "
            f"第{updated.target_payoff_chapter}章"
        )
        return 0

    if args.command == "alias":
        if args.alias_command == "list":
            aliases = store.list_item_aliases(project.id)
            if not aliases:
                print("（没有别名）")
            for item in aliases:
                print(f"{item.alias} -> {item.canonical_name}")
            return 0
        if args.alias_command == "set":
            item = store.upsert_item_alias(
                project.id, args.alias, args.canonical
            )
            print(f"已设置别名：{item.alias} -> {item.canonical_name}")
            return 0
        if not store.delete_item_alias(project.id, args.alias):
            raise KeyError(f"alias not found: {args.alias}")
        print(f"已删除别名：{args.alias}")
        return 0

    raise ValueError(f"unknown command: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        with MemoryStore(args.db) as store:
            store.migrate()
            return _run(parser, store, args)
    except (KeyError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
