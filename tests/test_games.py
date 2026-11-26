"""게임 패키지(overlay/games.py), 프레임(/frame), 장면 만들기의 게임 배치."""

import http.client
import json
from pathlib import Path

import pytest

from debutkit import cli, scenes
from debutkit.overlay import alerts, games, theme
from debutkit.overlay.server import OverlayServer

STATIC = Path(__file__).resolve().parent.parent / "src" / "debutkit" / "overlay" / "static"


def request(port, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response.status, response.getheader("Content-Type"), data


@pytest.fixture
def port():
    server = OverlayServer([], port=0).start()
    yield server.port
    server.stop()


def overlap(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return max(0, min(ax + aw, bx + bw) - max(ax, bx)) * max(0, min(ay + ah, by + bh) - max(ay, by)) / (aw * ah)


def test_every_package_is_complete_and_avoids_its_hud():
    assert set(cli.GAME_CHOICES) == set(games.GAMES)  # 명령줄 선택지와 같음
    for key, game in games.GAMES.items():
        assert game.style in theme.STYLES and game.alert in alerts.POSITIONS, key
        assert theme.check_color(game.primary, "주 색") and theme.check_color(game.highlight, "강조 색")
        for part in ("character", "chat", "goal", "rank"):
            x, y, w, h = getattr(game, part)
            assert x >= 0 and y >= 0 and x + w <= 1920 and y + h <= 1080 and w > 0 and h > 0, (key, part)
        assert game.hud and game.tips and all(len(tip) <= 60 for tip in game.tips), key  # 배치 요약은 짧은 항목
        # 채팅은 HUD와 겹치지 않고, 캐릭터는 게임 채팅처럼 가끔 뜨는 자리 말고는 거의 겹치지 않음
        assert max(overlap(game.chat, rect) for _, rect in game.hud) < 0.05, key
        assert max(overlap(game.character, rect) for _, rect in game.hud) < 0.5, key
    # 패키지마다 그 게임 이름의 게임별 스타일, 배경 그림, 그림 견본
    assert {key: game.style for key, game in games.GAMES.items()} == {key: key for key in games.GAMES}
    assert set(games.GAMES) == set(theme.GAME_LOOKS)
    for key in games.GAMES:
        assert (STATIC / "games" / f"scene-{key}.jpg").read_bytes()[:3] == b"\xff\xd8\xff", key
        record = json.loads((STATIC / "games" / "scenes.json").read_text(encoding="utf-8"))[key]  # 생성 기록(다시 만들 수 있게)
        assert record["license"].endswith("Apache-2.0") and record["prompt"] and isinstance(record["seed"], int), key
        assert "no logo" in record["prompt"] and games.GAMES[key].name not in record["prompt"], key  # 게임 이름, 로고 없이 장면만
        assert (STATIC / "games" / f"thumb-{key}.jpg").read_bytes()[:3] == b"\xff\xd8\xff", key


def test_frame_texts_are_checked():
    assert games.check_frames({"name": "  도토리   방송 ", "minutes": 5}) == {"name": "도토리 방송", "minutes": 5}
    for bad, message in (({"name": "가" * 31}, "이름표는 30자 이내"), ({"minutes": 121}, "0에서 120분"), ({"minutes": 1.5}, "정수"),
                         ({"minutes": True}, "정수"), ("x", "형식")):
        with pytest.raises(games.GameError, match=message):
            games.check_frames(bad)
    assert games.load() == {"game": "", "frames": games.FRAME_DEFAULTS}


def test_apply_package_sets_style_colors_alerts_and_layout(port):
    status, _, body = request(port, "GET", "/games")
    info = json.loads(body)
    assert status == 200 and info["game"] == "" and info["games"]["valorant"]["hud"][0]["label"] == "미니맵"

    status, _, body = request(port, "POST", "/games/apply", {"game": "valorant"})
    assert status == 200 and json.loads(body)["game"] == "valorant"
    saved = theme.load()
    assert saved["style"] == "valorant" and saved["primary"] == games.GAMES["valorant"].primary
    assert info["games"]["valorant"]["look"] == "valorant" and info["games"]["valorant"]["tips"][0].startswith("비우는 곳")
    assert alerts.load()["position"] == "left" and alerts.load()["style"] == "auto"

    # 배치만: 스타일과 알림은 그대로
    request(port, "POST", "/theme", {"style": "neon"})
    status, _, body = request(port, "POST", "/games/apply", {"game": "lol", "parts": ["layout"]})
    assert status == 200 and json.loads(body)["game"] == "lol" and theme.load()["style"] == "neon" and alerts.load()["position"] == "left"

    for bad, message in (({"game": "tetris"}, "없는 게임"), ({"game": "lol", "parts": ["sound"]}, "적용할 항목은"), ({"game": "lol", "parts": []}, "적용할 항목은")):
        status, _, body = request(port, "POST", "/games/apply", bad)
        assert status == 400 and message in json.loads(body)["error"]

    status, _, body = request(port, "POST", "/games/frames", {"name": "도토리 방송", "starting": "곧 시작", "minutes": 10})
    frames = json.loads(body)["frames"]
    assert status == 200 and frames["name"] == "도토리 방송" and frames["minutes"] == 10 and frames["brb"] == ""
    assert request(port, "POST", "/games/frames", {"note": "가" * 61})[0] == 400

    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", "/live?feeds=games")
    stream = conn.getresponse()
    assert stream.fp.readline().decode().strip() == "event: games"
    value = json.loads(stream.fp.readline().decode().removeprefix("data: "))
    assert value["game"] == "lol" and value["frames"]["starting"] == "곧 시작" and value["seq"] >= 3
    stream.close()
    conn.close()

    status, _, body = request(port, "POST", "/games/apply", {"game": ""})  # 기본 배치로(스타일은 그대로)
    assert status == 200 and json.loads(body)["game"] == "" and theme.load()["style"] == "neon"


def test_frame_pages(port):
    for path, marker in (("/frame", b"/frame.js"), ("/frame.js", b"debutkitLive.subscribe"), ("/frame.css", b".fr-box")):
        status, _, body = request(port, "GET", path)
        assert status == 200 and marker in body, path
    css = (STATIC / "frame.css").read_text(encoding="utf-8") + (STATIC / "games" / "look.css").read_text(encoding="utf-8")
    for style in theme.STYLES:  # 스타일마다 테두리와 모서리 장식(게임별 스타일은 games/look.css)
        assert f'data-dk-style="{style}"' in css or style == "prop" and 'html:not([data-dk-style])' in css, style
    script = (STATIC / "frame.js").read_text(encoding="utf-8")
    assert "textContent" in script and "innerHTML" not in script
    page = (STATIC / "stage.html").read_text(encoding="utf-8")
    assert '"/games/apply"' in page and '"/games/frames"' in page and "hud-box" in page and "/frame?kind=cam" in page
    assert "/games/thumb/" in page and "/games/scene/" in page and "srcOf(" in page


def test_game_looks_and_previews_are_served(port):
    look = (STATIC / "games" / "look.css").read_text(encoding="utf-8")
    for key in theme.GAME_LOOKS:  # 알림, 프레임, 대기 화면 배경을 게임마다
        for part in (".alert::before", ".fr-box", ".fr-plate", ".fr-panel"):
            assert f'html[data-dk-style="{key}"] {part}' in look, (key, part)
        assert f'url("/games/scene/{key}.jpg")' in look, key
    assert ":has(" not in look and "color-mix(" not in look  # OBS 28(Chromium 103)
    for page in ("alerts.html", "chat.html", "frame.html"):
        assert '<link rel="stylesheet" href="/games/look.css">' in (STATIC / page).read_text(encoding="utf-8"), page
    for path, kind in (("/games/look.css", "text/css"), ("/games/preview", "text/html"), ("/games/preview.js", "text/javascript"),
                       ("/games/avatar.svg", "image/svg+xml"), ("/games/scene/lol.jpg", "image/jpeg"), ("/games/thumb/lol.jpg", "image/jpeg")):
        status, content_type, _ = request(port, "GET", path)
        assert status == 200 and content_type.startswith(kind), path
    assert request(port, "GET", "/games/scene/tetris.jpg")[0] == 404
    preview = (STATIC / "games" / "preview.js").read_text(encoding="utf-8")
    assert "sample: \"1\"" in preview and "still: \"1\"" in preview and "/frame?" in preview and "innerHTML" not in preview
    # 채팅창 그림 견본(?sample): 예시 줄만, 연결하지 않음
    overlay = (STATIC / "overlay.js").read_text(encoding="utf-8")
    assert 'params.has("sample")' in overlay and "CHAT_SAMPLES" in overlay
    # 프레임은 그림 견본의 색을 이 화면만 바꿀 수 있음
    assert '"primary", "highlight"' in (STATIC / "frame.js").read_text(encoding="utf-8")


def items(scene):
    return {item.source: item for item in scene.items}


def test_scenes_follow_the_game_layout():
    kinds = scenes.default_kinds("Windows")
    plain = {scene.name: scene for scene in scenes.build_scenes(1920, 1080, kinds, scenes.SceneOptions(avatar="debutkit"))}
    assert not any("프레임" in item.source for scene in plain.values() for item in scene.items)  # 고르지 않으면 이전과 같음

    built = {scene.name: scene for scene in scenes.build_scenes(1920, 1080, kinds, scenes.SceneOptions(avatar="debutkit", game="valorant"))}
    main = items(built["본방송"])
    game = games.GAMES["valorant"]
    chat = main["[DK] 채팅 (게임 배치)"]
    assert (chat.transform["positionX"], chat.transform["positionY"], chat.transform["boundsWidth"]) == (game.chat[0], game.chat[1], game.chat[2])
    assert chat.settings["width"] == game.chat[2] and "[DK] 채팅" not in main
    assert chat.settings["url"].endswith("/chat?theme=style")  # 게임 배치 채팅은 게임 스타일 카드
    assert main["[DK] 캐릭터"].transform["positionX"] == game.character[0] and main["[DK] 캐릭터 프레임"].settings["url"].endswith("/frame?kind=cam")
    assert main["[DK] 목표 게이지"].transform["positionY"] == pytest.approx(game.goal[1])
    # 게임이 없는 장면은 오른쪽 세로 채팅 그대로, 대기와 자리 비움과 엔딩은 문구 대신 프레임 화면
    assert "[DK] 채팅" in items(built["토크"]) and "[DK] 채팅 (게임 배치)" not in items(built["토크"])
    for name, kind in (("대기 화면", "starting"), ("자리 비움", "brb"), ("엔딩", "ending")):
        sources = items(built[name])
        frame = next(item for item in sources.values() if item.settings.get("url", "").endswith(f"/frame?kind={kind}"))
        assert frame.role == "browser" and not any(item.role == "text" for item in sources.values())
    # 4K 캔버스는 비율대로
    big = {scene.name: scene for scene in scenes.build_scenes(3840, 2160, kinds, scenes.SceneOptions(avatar="debutkit", game="valorant"))}
    assert items(big["본방송"])["[DK] 채팅 (게임 배치)"].transform["positionX"] == game.chat[0] * 2
    # 프레임만(게임 없이)
    framed = {scene.name: scene for scene in scenes.build_scenes(1920, 1080, kinds, scenes.SceneOptions(avatar="debutkit", frames=True))}
    assert "[DK] 캐릭터 프레임" in items(framed["본방송"]) and "[DK] 채팅" in items(framed["본방송"])


def test_cli_dry_run_with_game(capsys):
    assert cli.main(["scenes", "--game", "lol", "--avatar", "debutkit", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "채팅 (게임 배치)" in out and "캐릭터 프레임" in out and "대기 화면 프레임" in out
