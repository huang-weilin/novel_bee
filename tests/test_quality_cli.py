import json

from novel_pipeline.quality.__main__ import main


def test_cli_log_only(tmp_path, capsys) -> None:
    chapter = tmp_path / "chapter.md"
    chapter.write_text("正文。", encoding="utf-8")
    code = main([str(chapter), "--mode", "log_only"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["decision"] == "accept"
    assert payload["notes"] == ["log_only"]
