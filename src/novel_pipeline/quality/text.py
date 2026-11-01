"""Text analysis helpers shared by programmatic rules."""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+")
_HR = re.compile(r"^\s*([-*_]\s*){3,}$")
_SENTENCE_END = re.compile(r"(?<=[。！？!?；;…])\s*")
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class TextStats:
    raw: str
    paragraphs: tuple[str, ...]
    paragraph_lengths: tuple[int, ...]
    sentences: tuple[str, ...]
    sentence_lengths: tuple[int, ...]
    sentence_counts: tuple[int, ...]
    char_count: int


def _split_paragraphs(text: str) -> tuple[str, ...]:
    kept: list[str] = []
    for line in text.splitlines():
        if _HEADING.match(line) or _HR.match(line):
            continue
        kept.append(line.rstrip())

    body = "\n".join(kept).strip()
    if not body:
        return ()

    parts = re.split(r"\n\s*\n", body)
    if len(parts) == 1:
        parts = [line for line in body.splitlines() if line.strip()]
    return tuple(part.strip() for part in parts if part.strip())


def _split_sentences(paragraph: str) -> tuple[str, ...]:
    parts = _SENTENCE_END.split(paragraph)
    return tuple(part.strip() for part in parts if part.strip())


def _content_length(text: str) -> int:
    return len(_WHITESPACE.sub("", text))


def analyze_text(text: str) -> TextStats:
    paragraphs = _split_paragraphs(text)
    sentences: list[str] = []
    sentence_counts: list[int] = []
    for paragraph in paragraphs:
        paragraph_sentences = _split_sentences(paragraph)
        sentence_counts.append(len(paragraph_sentences))
        sentences.extend(paragraph_sentences)

    paragraph_lengths = tuple(_content_length(p) for p in paragraphs)
    sentence_lengths = tuple(_content_length(s) for s in sentences)
    return TextStats(
        raw=text,
        paragraphs=paragraphs,
        paragraph_lengths=paragraph_lengths,
        sentences=tuple(sentences),
        sentence_lengths=sentence_lengths,
        sentence_counts=tuple(sentence_counts),
        char_count=sum(paragraph_lengths),
    )
