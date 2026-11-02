"""Checks for the download-and-run local distribution.

These do not start a server; they keep the start scripts, example config,
packaging metadata and documentation from drifting away from the actual
layout of the project.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "novel_pipeline" / "server" / "static"


def _text(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_start_scripts_launch_the_web_module() -> None:
    bat = _text("start.bat")
    sh = _text("start.sh")
    for source in (bat, sh):
        assert "novel_pipeline.server" in source
        assert "3.11" in source
        assert "pip install -e ." in source
    assert "py -3.12" in bat and "py -3.11" in bat
    assert "%*" in bat
    assert "python3.12" in sh and "python3.11" in sh
    assert '"$@"' in sh


def test_example_env_has_an_active_key_line() -> None:
    lines = _text(".env.example").splitlines()
    assert "NOVEL_LLM_API_KEY=" in lines
    assert "NOVEL_LLM_PROVIDER=deepseek" in lines
    assert not any(
        line.startswith("NOVEL_LLM_API_KEY=sk-") for line in lines
    ), "示例文件里不能出现真实 key"


def test_gitignore_covers_private_and_runtime_files() -> None:
    ignored = _text(".gitignore")
    for pattern in (".env", ".venv/", "data/*", "*.db", "references/"):
        assert pattern in ignored
    assert "!data/.gitkeep" in ignored
    assert "!.env.example" in ignored


def test_download_includes_required_runtime_files() -> None:
    for relative in (
        "config/quality.json",
        "data/.gitkeep",
        ".env.example",
        ".gitattributes",
        "README.md",
        "docs/LOCAL.md",
        "src/novel_pipeline/server/static/index.html",
        "src/novel_pipeline/server/static/app.js",
        "src/novel_pipeline/server/static/style.css",
    ):
        assert (ROOT / relative).is_file(), f"下载包缺少 {relative}"


def test_readme_covers_the_local_first_run() -> None:
    readme = _text("README.md")
    for needle in (
        "start.bat",
        "start.sh",
        "AI 设置",
        "数据",
        "备份",
        "127.0.0.1",
    ):
        assert needle in readme, f"README 缺少下载者需要的「{needle}」"


def test_pyproject_bounds_and_packages_static_files() -> None:
    project = _text("pyproject.toml")
    assert "pydantic>=2.6,<3" in project
    assert "fastapi>=0.115,<1" in project
    assert "uvicorn>=0.30,<1" in project
    assert 'novel_pipeline = ["server/static/*"]' in project


def test_gitattributes_keeps_script_line_endings() -> None:
    attributes = _text(".gitattributes")
    assert "*.sh text eol=lf" in attributes
    assert "*.bat text eol=crlf" in attributes


@pytest.mark.skipif(os.name == "nt", reason="Windows 不检查 POSIX 可执行位")
def test_start_sh_is_executable() -> None:
    assert os.access(ROOT / "start.sh", os.X_OK)


@pytest.mark.skipif(shutil.which("bash") is None, reason="本机没有 bash")
def test_start_sh_parses() -> None:
    result = subprocess.run(
        [shutil.which("bash"), "-n", str(ROOT / "start.sh")],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="本机没有 Node.js")
def test_web_ui_javascript_parses() -> None:
    node = shutil.which("node")
    result = subprocess.run(
        [node, "--check", str(STATIC / "app.js")],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
