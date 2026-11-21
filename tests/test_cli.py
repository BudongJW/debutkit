import pytest

from debutkit.cli import build_parser, main


def test_scenes_dry_run_needs_no_obs(capsys):
    assert main(["scenes", "--dry-run", "--avatar", "vseeface", "--overlay-port", "9000"]) == 0
    out = capsys.readouterr().out
    assert "본방송" in out and "아바타 (VSeeFace)" in out and "--dry-run" in out


def test_doctor_json(capsys, monkeypatch):
    from debutkit import doctor

    monkeypatch.setattr(doctor, "run_checks", lambda **kw: [doctor.Check("obs", "OBS Studio", doctor.OK, "found")])
    assert main(["doctor", "--json"]) == 0
    assert '"status": "ok"' in capsys.readouterr().out


def test_doctor_exit_code_on_required(capsys, monkeypatch):
    from debutkit import doctor

    monkeypatch.setattr(doctor, "run_checks", lambda **kw: [doctor.Check("obs", "OBS Studio", doctor.FAIL, "찾지 못함", "설치")])
    assert main(["doctor"]) == 1
    out = capsys.readouterr().out
    assert "[필요]" in out and "소속 버튜버 프로그램(선택)" in out and "무관" in out


def test_parser_requires_a_command():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])
