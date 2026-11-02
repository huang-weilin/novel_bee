"""Launch the local web app.

Examples:
    python -m novel_pipeline.server
    python -m novel_pipeline.server --port 8123 --no-browser
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser

from ..envfile import load_env_file
from .app import _DEFAULT_DATA_PATH, _DEFAULT_QUALITY_MODE, create_app
from .schemas import QUALITY_MODES


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if not 1 <= parsed <= 65535:
        raise argparse.ArgumentTypeError("must be between 1 and 65535")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="novel-pipeline",
        description="长篇小说工坊本地网页版",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("NOVEL_SERVER_HOST", "127.0.0.1"),
        help="监听地址，默认 127.0.0.1（只允许本机访问）",
    )
    parser.add_argument(
        "--port",
        type=_positive_int,
        default=int(os.getenv("NOVEL_SERVER_PORT", "8000")),
        help="监听端口，默认 8000",
    )
    parser.add_argument(
        "--data",
        default=os.getenv("NOVEL_DATA_PATH", _DEFAULT_DATA_PATH),
        help="SQLite 数据库路径，默认 data/novel.db",
    )
    parser.add_argument(
        "--quality-mode",
        choices=QUALITY_MODES,
        default=os.getenv("NOVEL_QUALITY_MODE", _DEFAULT_QUALITY_MODE),
        help="质量门模式，默认 full",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="启动后不自动打开浏览器",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_env_file(".env")
    args = _parser().parse_args(argv)

    local_host = args.host in ("127.0.0.1", "localhost", "::1")
    if not local_host:
        print(
            "WARNING: the local server has no login. Bind 127.0.0.1 unless "
            "you put an authenticated reverse proxy in front of it.",
            flush=True,
        )

    app = create_app(
        data_path=args.data,
        default_quality_mode=args.quality_mode,
    )
    browser_host = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    url = f"http://{browser_host}:{args.port}"
    print(f"Novel Pipeline local app: {url}", flush=True)
    print(f"Data: {args.data}", flush=True)
    print(f"Quality mode: {args.quality_mode}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    import uvicorn

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=os.getenv("NOVEL_SERVER_LOG_LEVEL", "info"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
