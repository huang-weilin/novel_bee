"""Static checks for the no-build WeChat mini-program.

The mini-program talks to the same local HTTP API as the browser UI, so these
tests keep the page registration, navigation targets and endpoint names in
sync without needing WeChat DevTools in CI.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "miniprogram"


def _read_json(name: str) -> dict:
    return json.loads((MINI / name).read_text(encoding="utf-8"))


def _page_targets() -> set[str]:
    pattern = re.compile(r"""["'](/pages/[a-z0-9_]+/[a-z0-9_]+)""")
    targets: set[str] = set()
    for path in MINI.rglob("*.js"):
        targets.update(pattern.findall(path.read_text(encoding="utf-8")))
    return targets


def test_every_registered_page_has_all_files() -> None:
    pages = _read_json("app.json")["pages"]
    assert pages, "小程序至少要注册一个页面"
    for page in pages:
        for suffix in ("js", "json", "wxml", "wxss"):
            path = MINI / f"{page}.{suffix}"
            assert path.is_file(), f"缺少页面文件：{path}"


def test_navigation_targets_are_registered() -> None:
    pages = set(_read_json("app.json")["pages"])
    targets = _page_targets()
    assert targets, "没有找到任何 wx.navigateTo/redirectTo 目标"
    missing = sorted(target for target in targets if target.lstrip("/") not in pages)
    assert not missing, f"跳转到了未注册的页面：{missing}"


def test_project_config_is_devtools_friendly() -> None:
    config = _read_json("project.config.json")
    assert config["miniprogramRoot"] == "./"
    assert config["compileType"] == "miniprogram"
    # 本地 http 后端需要关闭合法域名校验；真机发布前应改为 https 域名。
    assert config["setting"]["urlCheck"] is False
    assert "appsecret" not in json.dumps(config).lower()


def test_api_module_covers_the_three_gates() -> None:
    source = (MINI / "utils" / "api.js").read_text(encoding="utf-8")
    for needle in (
        "/api/health",
        "/api/genres",
        "/api/projects",
        "/chapters/generate",
        "/chapters/trial",
        "/characters",
        "/items",
        "/export",
        "/api/jobs/",
    ):
        assert needle in source, f"小程序 API 缺少 {needle}"
    for method in (
        "generate(",
        "trial(",
        "getJob(",
        "registerCharacter(",
        "registerItem(",
    ):
        assert method in source, f"小程序 API 缺少方法 {method}"


def test_three_confirmation_screens_are_wired() -> None:
    outline = (MINI / "pages" / "outline" / "outline.wxml").read_text(
        encoding="utf-8"
    )
    trial = (MINI / "pages" / "trial" / "trial.wxml").read_text(encoding="utf-8")
    chapter = (MINI / "pages" / "chapter" / "chapter.wxml").read_text(
        encoding="utf-8"
    )
    assert "startTrial" in outline and "startGenerate" in outline
    assert "confirmTrial" in trial and "retryTrial" in trial
    assert "registerCharacter" in chapter and "registerItem" in chapter
    assert "待确认" in chapter and "重写本章" in chapter
    assert "内容由 AI 生成" in chapter and "内容由 AI 生成" in trial


def test_chapter_page_handles_jobs_and_review_forms() -> None:
    source = (MINI / "pages" / "chapter" / "chapter.js").read_text(
        encoding="utf-8"
    )
    assert "waitForJob" in source
    assert "review_items" in source
    assert "registerCharacter" in source and "registerItem" in source
    assert "statusLabel" in source and "statusClass" in source


@pytest.mark.skipif(shutil.which("node") is None, reason="本机没有 Node.js")
def test_mini_program_javascript_parses() -> None:
    node = shutil.which("node")
    assert node is not None
    files = sorted(MINI.rglob("*.js"))
    assert files
    for path in files:
        result = subprocess.run(
            [node, "--check", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"{path} 语法错误：{result.stderr}"
