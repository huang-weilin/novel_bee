from pathlib import Path

from novel_pipeline.envfile import load_env_file, parse_env


def test_parse_env_supports_comments_quotes_and_export() -> None:
    values = parse_env(
        """
        # comment
        NOVEL_LLM_PROVIDER=deepseek
        export NOVEL_LLM_MODEL="deepseek-chat"
        EMPTY=
        WITH_COMMENT=value # trailing comment
        QUOTED_COMMENT="a # b"
        """
    )
    assert values == {
        "NOVEL_LLM_PROVIDER": "deepseek",
        "NOVEL_LLM_MODEL": "deepseek-chat",
        "EMPTY": "",
        "WITH_COMMENT": "value",
        "QUOTED_COMMENT": "a # b",
    }


def test_parse_env_strips_utf8_bom() -> None:
    values = parse_env("﻿NOVEL_LLM_PROVIDER=deepseek\nNOVEL_LLM_MODEL=deepseek-chat\n")
    assert values["NOVEL_LLM_PROVIDER"] == "deepseek"
    assert values["NOVEL_LLM_MODEL"] == "deepseek-chat"


def test_load_env_file_does_not_override_by_default(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("A=file\nB=file\n", encoding="utf-8")
    env = {"A": "shell"}

    applied = load_env_file(path, environ=env)

    assert env == {"A": "shell", "B": "file"}
    assert applied == {"B": "file"}


def test_load_env_file_can_override(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("A=file\n", encoding="utf-8")
    env = {"A": "shell"}

    applied = load_env_file(path, environ=env, override=True)

    assert env["A"] == "file"
    assert applied == {"A": "file"}


def test_missing_env_file_is_not_an_error(tmp_path: Path) -> None:
    assert load_env_file(tmp_path / "missing.env", environ={}) == {}
