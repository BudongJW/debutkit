"""방송 연출 명령줄: debutkit pick, wall, race(실행 중인 오버레이)와 추첨의 새 설정 항목."""

import pytest

from debutkit import draw
from debutkit.cli import main
from debutkit.overlay.server import OverlayServer


@pytest.fixture
def port():
    server = OverlayServer([], port=0).start()
    yield str(server.port)
    server.stop()


def test_pick_commands(port, capsys):
    assert main(["pick", "--port", port, "status"]) == 0 and "0/20칸 열림, 방송에 표시 중" in capsys.readouterr().out
    assert main(["pick", "--port", port, "open", "5", "--by", "치즈냥"]) == 0 and "5번 칸:" in capsys.readouterr().out
    assert main(["pick", "--port", port, "hide"]) == 0 and "방송에서 숨김" in capsys.readouterr().out
    assert main(["pick", "--port", port, "open", "99"]) == 1


def test_wall_commands(port, capsys, tmp_path):
    assert main(["wall", "--port", port, "test", "--unit", "별풍선", "--amount", "100"]) == 0 and "시험 카드 1장" in capsys.readouterr().out
    assert main(["wall", "--port", port, "status"]) == 0 and "카드 1장(시험 1장)" in capsys.readouterr().out
    out = tmp_path / "wall.txt"
    assert main(["wall", "--port", port, "export", "--out", str(out)]) == 0 and "별풍선" in out.read_text(encoding="utf-8")
    assert main(["wall", "--port", port, "clear-tests"]) == 0 and "카드 0장" in capsys.readouterr().out


def test_race_commands(port, capsys):
    assert main(["race", "--port", port, "start", "--practice", "--game", "run"]) == 0 and "경기 중" in capsys.readouterr().out
    assert main(["race", "--port", port, "stop"]) == 0 and "대기" in capsys.readouterr().out
    assert main(["race", "--port", "1", "status"]) == 1  # 오버레이 없음


def test_draw_set_new_look_settings(capsys):
    assert main(["draw", "set", "--style", "capsule", "--effect", "stars", "--name-font", "text", "--name-size", "large"]) == 0
    config = draw.load_config()
    assert (config.style, config.design, config.effect, config.name_font, config.name_size) == ("capsule", "round", "stars", "pretendard", "large")
    assert "모양 둥근 유리 돔" in capsys.readouterr().out
    assert main(["draw", "set", "--style", "tarot", "--advice-line", "오늘은 좋은 날", "--advice-line", "물 많이 마시기"]) == 0
    assert draw.load_config().advice_lines == ["오늘은 좋은 날", "물 많이 마시기"] and draw.load_config().effect == "stars"  # 지정하지 않은 항목은 유지
    assert main(["draw", "set", "--design", "없는모양"]) == 1
