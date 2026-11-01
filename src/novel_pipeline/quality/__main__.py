"""Run the quality gate against a chapter file.

Usage:
    python -m novel_pipeline.quality data/m1-chapter-2000.md --mode rules
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .adapter import QualityAdapter
from .models import ChapterInput
from .scorer import LLMScorer
from .verifier import LLMVerifier


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m novel_pipeline.quality")
    parser.add_argument("chapter", type=Path, help="UTF-8 chapter file")
    parser.add_argument(
        "--mode",
        choices=("log_only", "rules", "rules+llm", "rules+score", "full"),
        default="rules",
    )
    parser.add_argument("--genre", default="")
    parser.add_argument("--project-id", default="")
    parser.add_argument("--chapter-seq", type=int, default=0)
    parser.add_argument("--log-file", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    text = args.chapter.read_text(encoding="utf-8")

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if args.log_file:
        handlers.append(logging.FileHandler(args.log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )

    verifier = LLMVerifier() if args.mode in ("rules+llm", "full") else None
    scorer = LLMScorer() if args.mode in ("rules+score", "full") else None
    adapter = QualityAdapter(verifier=verifier, scorer=scorer)
    report = adapter.review(
        ChapterInput(
            content=text,
            project_id=args.project_id,
            chapter_seq=args.chapter_seq,
            genre=args.genre,
        ),
        mode=args.mode,
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.decision.value == "accept" else 1


if __name__ == "__main__":
    raise SystemExit(main())
