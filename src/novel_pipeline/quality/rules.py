"""Programmatic quality rules Q01-Q06, Q11, and Q12.

Thresholds live in ``config/quality.json``. Rule IDs and wording are this
project's own; they are not copied from any reference repository.
"""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from .models import RuleFinding, Severity
from .text import TextStats, analyze_text

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "config" / "quality.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "q01": {
        "min_paragraphs": 8,
        "max_consecutive_single_sentence": 2,
        "max_single_sentence_ratio": 0.30,
    },
    "q02": {"min_paragraphs": 20, "min_length_cv": 0.25},
    "q03": {"max_emphasis_per_1000": 6.0, "max_headings_per_500": 1.0},
    "q04": {
        "max_hits_per_1000": 5.0,
        "phrases": [
            "总之",
            "综上所述",
            "值得注意的是",
            "与此同时",
            "毫无疑问",
            "显而易见",
            "换句话说",
            "不禁",
            "若有所思",
            "深吸一口气",
            "微微一笑",
            "缓缓地",
            "淡淡地",
            "默默地",
            "这一刻",
            "那一刻",
            "不知为何",
        ],
    },
    "q05": {
        "min_sentences": 20,
        "common_sentence_min": 15,
        "common_sentence_max": 35,
        "max_common_ratio": 0.75,
        "min_avg_length": 12,
    },
    "q06": {"n": 4, "max_repeat": 3, "min_chars": 400},
    "q11": {},
    "q12": {"min_ratio": 0.7, "max_ratio": 1.3},
}


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load rule config, falling back to built-in defaults."""
    config_path = Path(path) if path else _DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return json.loads(json.dumps(DEFAULT_CONFIG))
    with config_path.open(encoding="utf-8") as handle:
        loaded = json.load(handle)
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    for key, section in loaded.items():
        if isinstance(section, dict) and isinstance(merged.get(key), dict):
            merged[key].update(section)
        else:
            merged[key] = section
    return merged


def _max_single_sentence_run(flags: list[bool]) -> tuple[int, int, int]:
    best = 0
    best_start = best_end = 0
    current = 0
    start = 0
    for index, flag in enumerate(flags):
        if flag:
            if current == 0:
                start = index
            current += 1
            if current > best:
                best = current
                best_start, best_end = start, index
        else:
            current = 0
    return best, best_start, best_end


class Q01:
    rule_id = "Q01"
    # 单句段本身不是缺陷：真实网文常用短段推进对话和动作节拍。
    # 降为提示级，避免把“有意的节奏”误判成“碎片化”并强制改写。
    severity = Severity.MINOR

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def check(self, stats: TextStats) -> RuleFinding | None:
        cfg = self.config
        if len(stats.paragraphs) < int(cfg.get("min_paragraphs", 8)):
            return None
        flags = [count <= 1 for count in stats.sentence_counts]
        max_run, start, end = _max_single_sentence_run(flags)
        ratio = sum(flags) / len(flags)
        trigger_run = max_run > int(cfg.get("max_consecutive_single_sentence", 2))
        trigger_ratio = ratio > float(cfg.get("max_single_sentence_ratio", 0.30))
        if not (trigger_run or trigger_ratio):
            return None
        return RuleFinding(
            rule_id=self.rule_id,
            severity=self.severity,
            evidence=(
                f"连续单句段 {max_run} 段（第 {start + 1}-{end + 1} 段），"
                f"单句段占比 {ratio:.0%}"
            ),
            suggestion=(
                "单句段较多。若这些短段是连续的对话或动作节拍，可以保留；"
                "只有读起来像提纲、段与段之间没有推进时，才合并并补充场景。"
            ),
            metrics={"max_run": max_run, "ratio": round(ratio, 4)},
        )


class Q02:
    rule_id = "Q02"
    severity = Severity.MAJOR

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def check(self, stats: TextStats) -> RuleFinding | None:
        cfg = self.config
        lengths = stats.paragraph_lengths
        if len(lengths) < int(cfg.get("min_paragraphs", 20)):
            return None
        mean = statistics.fmean(lengths)
        if mean <= 0:
            return None
        cv = statistics.pstdev(lengths) / mean
        if cv >= float(cfg.get("min_length_cv", 0.25)):
            return None
        return RuleFinding(
            rule_id=self.rule_id,
            severity=self.severity,
            evidence=(
                f"{len(lengths)} 段长度变异系数 {cv:.2f}，"
                f"平均 {mean:.0f} 字，段落过于均匀"
            ),
            suggestion="调整段落长短，让叙事节奏有呼吸感。",
            metrics={"paragraphs": len(lengths), "cv": round(cv, 4), "mean": round(mean, 2)},
        )


class Q03:
    rule_id = "Q03"
    severity = Severity.MAJOR

    _BOLD = re.compile(r"\*\*[^*\n]+\*\*")
    _ITALIC = re.compile(r"(?<!\*)\*[^*\n]+\*(?!\*)")
    _UNDERLINE = re.compile(r"__[^_\n]+__")
    _HEADING_LINE = re.compile(r"^\s{0,3}#{1,6}\s+")

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def check(self, stats: TextStats) -> RuleFinding | None:
        cfg = self.config
        raw = stats.raw
        emphasis = (
            len(self._BOLD.findall(raw))
            + len(self._ITALIC.findall(raw))
            + len(self._UNDERLINE.findall(raw))
        )
        headings = sum(1 for line in raw.splitlines() if self._HEADING_LINE.match(line))
        if stats.char_count <= 0:
            return None
        emphasis_per_1000 = emphasis / (stats.char_count / 1000)
        headings_per_500 = headings / (stats.char_count / 500)
        if (
            emphasis_per_1000 <= float(cfg.get("max_emphasis_per_1000", 6.0))
            and headings_per_500 <= float(cfg.get("max_headings_per_500", 1.0))
        ):
            return None
        return RuleFinding(
            rule_id=self.rule_id,
            severity=self.severity,
            evidence=(
                f"强调标记 {emphasis} 处（{emphasis_per_1000:.1f}/千字），"
                f"小标题 {headings} 个（{headings_per_500:.1f}/500字）"
            ),
            suggestion="减少粗体、斜体和小标题，用叙述本身承担强调。",
            metrics={
                "emphasis": emphasis,
                "headings": headings,
                "emphasis_per_1000": round(emphasis_per_1000, 3),
                "headings_per_500": round(headings_per_500, 3),
            },
        )


class Q04:
    rule_id = "Q04"
    severity = Severity.MAJOR

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def check(self, stats: TextStats) -> RuleFinding | None:
        cfg = self.config
        phrases: list[str] = list(cfg.get("phrases", []))
        if not phrases or stats.char_count <= 0:
            return None
        counts = {phrase: stats.raw.count(phrase) for phrase in phrases}
        hits = sum(counts.values())
        density = hits / (stats.char_count / 1000)
        if density <= float(cfg.get("max_hits_per_1000", 5.0)):
            return None
        top = sorted(
            ((phrase, count) for phrase, count in counts.items() if count),
            key=lambda item: item[1],
            reverse=True,
        )[:5]
        detail = "、".join(f"{phrase}×{count}" for phrase, count in top)
        return RuleFinding(
            rule_id=self.rule_id,
            severity=self.severity,
            evidence=f"套话/连接词命中 {hits} 次（{density:.1f}/千字）：{detail}",
            suggestion="删除套话连接词，用动作、画面或场景切换代替。",
            metrics={"hits": hits, "density": round(density, 3)},
        )


class Q05:
    rule_id = "Q05"
    severity = Severity.MINOR

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def check(self, stats: TextStats) -> RuleFinding | None:
        cfg = self.config
        lengths = stats.sentence_lengths
        if len(lengths) < int(cfg.get("min_sentences", 20)):
            return None
        low = int(cfg.get("common_sentence_min", 15))
        high = int(cfg.get("common_sentence_max", 35))
        common = sum(1 for length in lengths if low <= length <= high)
        ratio = common / len(lengths)
        average = statistics.fmean(lengths)
        trigger_ratio = ratio > float(cfg.get("max_common_ratio", 0.75))
        trigger_avg = average < float(cfg.get("min_avg_length", 12))
        if not (trigger_ratio or trigger_avg):
            return None
        return RuleFinding(
            rule_id=self.rule_id,
            severity=self.severity,
            evidence=(
                f"{len(lengths)} 句中 {low}-{high} 字句占 {ratio:.0%}，"
                f"平均句长 {average:.1f} 字"
            ),
            suggestion="穿插短句与长句，调整句长节奏。",
            metrics={"ratio": round(ratio, 4), "avg_length": round(average, 2)},
        )


class Q06:
    rule_id = "Q06"
    severity = Severity.MINOR

    _CJK = re.compile(r"[一-鿿]")

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def check(self, stats: TextStats) -> RuleFinding | None:
        cfg = self.config
        chars = self._CJK.findall(stats.raw)
        if len(chars) < int(cfg.get("min_chars", 400)):
            return None
        n = int(cfg.get("n", 4))
        if len(chars) <= n:
            return None
        counter = Counter("".join(chars[i : i + n]) for i in range(len(chars) - n + 1))
        gram, count = counter.most_common(1)[0]
        if count <= int(cfg.get("max_repeat", 3)):
            return None
        return RuleFinding(
            rule_id=self.rule_id,
            severity=self.severity,
            evidence=f"四字片段“{gram}”重复 {count} 次",
            suggestion="替换重复措辞，避免同一短语反复出现。",
            metrics={"repeat": count, "n": n},
        )


_CJK_RANGE = "㐀-䶿一-鿿豈-﫿"
_CJK = f"[{_CJK_RANGE}]"


def _snippet(raw: str, start: int, end: int, *, radius: int = 8) -> str:
    left = max(0, start - radius)
    right = min(len(raw), end + radius)
    return re.sub(r"\s+", " ", raw[left:right]).strip()


class Q11:
    rule_id = "Q11"
    severity = Severity.MAJOR

    # 中文语境内使用半角标点，或把中文对话包在直引号里。只查紧邻汉字的
    # 情况，避免把英文术语、数字和代码里的半角符号误判为中文排版问题。
    _HALF_BETWEEN = re.compile(
        rf"(?<={_CJK})[,\.!?;:](?={_CJK}|[\s”’」』）\]】》〉\"']|$)"
    )
    _ELLIPSIS = re.compile(rf"(?<={_CJK})\.{{3,}}(?={_CJK})")
    _DASH = re.compile(rf"(?<={_CJK})--+(?={_CJK})")
    _DOUBLE_PAIR = re.compile(rf'"[^"\n]*{_CJK}[^"\n]*"')
    _DOUBLE_ADJ = re.compile(rf'(?<={_CJK})"|"(?={_CJK})')
    _SINGLE_PAIR = re.compile(rf"'[^'\n]*{_CJK}[^'\n]*'")
    _SINGLE_ADJ = re.compile(rf"(?<={_CJK})'|'(?={_CJK})")

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def check(self, stats: TextStats) -> RuleFinding | None:
        raw = stats.raw
        half = list(self._HALF_BETWEEN.finditer(raw))
        ellipsis = list(self._ELLIPSIS.finditer(raw))
        dash = list(self._DASH.finditer(raw))
        double_pair = list(self._DOUBLE_PAIR.finditer(raw))
        double_adj = list(self._DOUBLE_ADJ.finditer(raw))
        single_pair = list(self._SINGLE_PAIR.finditer(raw))
        single_adj = list(self._SINGLE_ADJ.finditer(raw))

        half_count = len(half) + len(ellipsis) + len(dash)
        double_count = 0
        if double_pair or double_adj:
            double_count = max(
                len(double_pair) * 2, len(double_adj), raw.count('"')
            )
        single_count = max(len(single_pair) * 2, len(single_adj))
        if not (half_count or double_count or single_count):
            return None

        samples: list[str] = []
        for match in (half + ellipsis + dash)[:3]:
            samples.append(_snippet(raw, match.start(), match.end()))
        if double_pair:
            match = double_pair[0]
            samples.append(_snippet(raw, match.start(), match.end(), radius=0)[:40])
        elif double_adj:
            match = double_adj[0]
            samples.append(_snippet(raw, match.start(), match.end()))
        if single_pair:
            match = single_pair[0]
            samples.append(_snippet(raw, match.start(), match.end(), radius=0)[:40])

        parts: list[str] = []
        if half_count:
            parts.append(f"半角标点 {half_count} 处")
        if double_count:
            parts.append(f"直双引号 {double_count} 个")
        if single_count:
            parts.append(f"直单引号 {single_count} 个")
        detail = "；".join(f"“{sample}”" for sample in dict.fromkeys(samples))
        evidence = "，".join(parts)
        if detail:
            evidence += f"：{detail}"

        return RuleFinding(
            rule_id=self.rule_id,
            severity=self.severity,
            evidence=evidence,
            suggestion=(
                "中文语境改用全角标点（，。！？；：），省略号用“……”，"
                "破折号用“——”，直引号换成“”；只改标点，不改句子。"
            ),
            metrics={
                "halfwidth": half_count,
                "straight_double": double_count,
                "straight_single": single_count,
            },
        )


class Q12:
    rule_id = "Q12"
    severity = Severity.MINOR

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def check(self, stats: TextStats, *, target_words: int) -> RuleFinding | None:
        cfg = self.config
        if target_words <= 0:
            return None
        low_ratio = float(cfg.get("min_ratio", 0.7))
        high_ratio = float(cfg.get("max_ratio", 1.3))
        low = round(target_words * low_ratio)
        high = round(target_words * high_ratio)
        count = stats.char_count
        if low <= count <= high:
            return None
        direction = "低于" if count < low else "高于"
        suggestion = (
            "篇幅偏低：补一段有目标的场景（冲突、代价或钩子），不要用解释和形容词凑字数。"
            if count < low
            else "篇幅偏高：先删重复解释和可推断的细节；若情节确实需要，考虑拆成两章，不要硬压。"
        )
        return RuleFinding(
            rule_id=self.rule_id,
            severity=self.severity,
            evidence=(
                f"本章 {count} 字，目标 {target_words} 字，{direction}容差区间 "
                f"{low}-{high} 字"
            ),
            suggestion=suggestion,
            metrics={
                "chars": count,
                "target_words": target_words,
                "ratio": round(count / target_words, 3),
                "min_ratio": low_ratio,
                "max_ratio": high_ratio,
            },
        )


_RULE_CLASSES = (Q01, Q02, Q03, Q04, Q05, Q06, Q11)
_SEVERITY_ORDER = {Severity.BLOCKER: 0, Severity.MAJOR: 1, Severity.MINOR: 2}


class RuleEngine:
    """Run programmatic rules against a chapter."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or load_config()
        self.rules = [
            rule_class(self.config[rule_class.rule_id.lower()])
            for rule_class in _RULE_CLASSES
        ]
        self.length_rule = Q12(self.config["q12"])

    @classmethod
    def from_config_file(cls, path: str | Path) -> RuleEngine:
        return cls(load_config(path))

    def check(
        self,
        text: str,
        *,
        genre: str = "",
        target_words: int | None = None,
    ) -> list[RuleFinding]:
        stats = analyze_text(text)
        findings = [
            finding
            for rule in self.rules
            if (finding := rule.check(stats)) is not None
        ]
        if target_words and target_words > 0:
            finding = self.length_rule.check(stats, target_words=target_words)
            if finding is not None:
                findings.append(finding)
        return sorted(findings, key=lambda item: _SEVERITY_ORDER[item.severity])
