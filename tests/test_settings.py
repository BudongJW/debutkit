"""설정 저장: 저장 가능한 항목만 기록, 비밀값 제외, 손상된 파일 무시."""

import json

from debutkit import settings


def test_round_trip_keeps_only_known_fields(tmp_path):
    path = tmp_path / "settings.json"
    settings.save({"chzzk": ["https://chzzk.naver.com/live/abc", " "], "demo": True, "overlay_port": 8790, "youtube_interval": 15,
                   "unknown": 1, "overlay_port_text": "x"}, path)
    assert settings.load(path) == {"chzzk": ["https://chzzk.naver.com/live/abc"], "demo": True, "overlay_port": 8790, "youtube_interval": 15.0}
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == settings.VERSION


def test_secrets_are_never_written(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setitem(settings.FIELDS, "youtube_key", str)  # 실수로 항목을 추가해도 저장하지 않음
    settings.save({"youtube_key": "AIza-secret", "obs_password": "pw", "chzzk_client_secret": "s", "chzzk_client_id": "id"}, path)
    text = path.read_text(encoding="utf-8")
    assert "AIza-secret" not in text and "pw" not in text and '"s"' not in text
    assert settings.load(path) == {"chzzk_client_id": "id"}


def test_wrong_types_and_broken_files_are_ignored(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"version": 1, "settings": {"demo": "yes", "overlay_port": True, "soop": "id", "youtube_interval": "10"}}), encoding="utf-8")
    assert settings.load(path) == {"soop": ["id"]}
    path.write_text("{broken", encoding="utf-8")
    assert settings.load(path) == {}
    assert settings.load(tmp_path / "missing.json") == {}


def test_location_and_clear(tmp_path, monkeypatch):
    monkeypatch.setenv("DEBUTKIT_SETTINGS", str(tmp_path / "x" / "s.json"))
    assert settings.settings_path() == tmp_path / "x" / "s.json"
    written = settings.save({"demo": True})
    assert written.is_file() and not written.with_name("s.json.tmp").exists()
    assert settings.clear() == written and settings.clear() is None
    monkeypatch.delenv("DEBUTKIT_SETTINGS")
    assert settings.settings_path().parts[-2:] == ("debutkit", "settings.json")


def test_overlay_saved_fills_only_unspecified_options(tmp_path, monkeypatch, capsys):
    from debutkit import cli

    monkeypatch.setenv("DEBUTKIT_SETTINGS", str(tmp_path / "settings.json"))
    settings.save({"chzzk": ["https://chzzk.naver.com/live/abc"], "overlay_port": 8800, "clip": True, "youtube_mode": "poll", "avatar_app": "vts"})
    args = cli.build_parser().parse_args(["overlay", "--saved", "--port", "9000"])
    cli._overlay_settings(args)
    assert args.chzzk == ["https://chzzk.naver.com/live/abc"] and args.clip is True and args.youtube_mode == "poll"
    assert args.port == 9000  # 명령줄 지정 우선
    assert "저장한 설정 사용(3개 항목)" in capsys.readouterr().out


def test_overlay_save_keeps_wizard_only_fields(tmp_path, monkeypatch, capsys):
    from debutkit import cli

    monkeypatch.setenv("DEBUTKIT_SETTINGS", str(tmp_path / "settings.json"))
    settings.save({"avatar_app": "vseeface", "soop": ["old"]})
    args = cli.build_parser().parse_args(["overlay", "--save", "--soop", "new", "--clip", "--youtube-key", "AIza-secret"])
    cli._overlay_settings(args)
    saved = settings.load()
    assert saved["soop"] == ["new"] and saved["clip"] is True and saved["avatar_app"] == "vseeface"
    assert "AIza-secret" not in (tmp_path / "settings.json").read_text(encoding="utf-8")
    assert "API 키, 비밀번호는 저장하지 않음" in capsys.readouterr().out


def test_settings_command_shows_and_clears(tmp_path, monkeypatch, capsys):
    from debutkit import cli

    monkeypatch.setenv("DEBUTKIT_SETTINGS", str(tmp_path / "settings.json"))
    assert cli.main(["settings"]) == 0 and "(없음)" in capsys.readouterr().out
    settings.save({"demo": True})
    assert cli.main(["settings"]) == 0 and '"demo": true' in capsys.readouterr().out
    assert cli.main(["settings", "--clear"]) == 0 and "삭제" in capsys.readouterr().out
    assert not (tmp_path / "settings.json").exists()
