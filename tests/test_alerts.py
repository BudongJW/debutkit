"""후원 알림 꾸미기(overlay/alerts.py): 설정 확인, 금액 구간, 그림, 조작 화면과 방송 화면."""

import base64
import http.client
import json
from pathlib import Path

import pytest

from debutkit import settings
from debutkit.overlay import alerts
from debutkit.overlay.server import OverlayServer

STATIC = Path(__file__).resolve().parent.parent / "src" / "debutkit" / "overlay" / "static"
PNG = b"\x89PNG\r\n\x1a\n" + bytes(32)


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


def test_defaults_and_choices():
    config = alerts.load()
    assert {key: config[key] for key in alerts.DEFAULTS} == alerts.DEFAULTS
    assert set(alerts.STYLES) - {"auto"} == set(alerts.theme.STYLES)
    assert len(alerts.LAYOUTS) >= 6 and len(alerts.POSITIONS) == 9 and len(alerts.SOUNDS) >= 5 and len(alerts.EMPHASIS) >= 5
    assert set(alerts.ENTERS) - {"auto"} == set(alerts.theme.ENTERS)  # 방송 스타일의 등장 움직임과 같은 이름


def test_korean_particles_follow_the_last_syllable():
    assert alerts._josa("배치", "은", "는") == "배치는" and alerts._josa("스타일", "은", "는") == "스타일은"
    assert alerts._josa("크기(%)", "은", "는") == "크기(%)는" and alerts._josa("구간 최소 금액(원)", "은", "는") == "구간 최소 금액(원)은"
    assert alerts._josa("후원 문구", "이", "가") == "후원 문구가"


@pytest.mark.parametrize("changes, message", [
    ({"layout": "zigzag"}, "배치는 card, banner"),
    ({"position": "middle"}, "위치는 top-left"),
    ({"style": "rainbow"}, "스타일은 auto, prop"),
    ({"enter": "spin"}, "등장은 auto, stamp"),
    ({"seconds": 2}, r"표시 시간\(초\)는 3에서 30 사이의 정수"),
    ({"seconds": 6.5}, "3에서 30 사이의 정수"),
    ({"scale": 200}, r"크기\(%\)는 60에서 160"),
    ({"volume": True}, "소리 크기는 0에서 100"),
    ({"sound": "airhorn"}, "효과음은 none, chime"),
    ({"title": " "}, "후원 문구가 비어 있음"),
    ({"title": "가" * 81}, "80자 이내"),
    ({"title": "{nick} 님 감사"}, r"쓸 수 있는 자리는 \{name\}\(이름\), \{amount\}\(금액\): \{nick\}"),
    ({"member_title": "{name} {amount} {x}"}, "구독 문구에 쓸 수 있는 자리는"),
    ({"member_image": "a" * 24}, "없는 그림"),
    ({"tiers": {"min": 0}}, "금액 구간은 목록"),
    ({"tiers": [{"min": 1000}, {"min": 1000}]}, "같은 금액의 구간이 2개: 1,000원"),
    ({"tiers": [{"min": -1}]}, r"구간 최소 금액\(원\)은 0에서"),
    ({"tiers": [{"min": 0, "emphasis": "boom"}]}, "강조 효과는 none, sparkle"),
    ({"tiers": [{"min": 0, "seconds": 99}]}, "구간 표시 시간은 3에서 30"),
    ({"tiers": [{"min": 0, "image": "b" * 24}]}, "없는 그림"),
    ({"tiers": [{"min": n} for n in range(13)]}, "12개까지"),
])
def test_bad_settings_are_explained(changes, message):
    with pytest.raises(alerts.AlertError, match=message):
        alerts.update(alerts.load(), changes, [])


def test_tiers_are_sorted_from_the_biggest():
    tiers = alerts.check_tiers([{"min": 0}, {"min": 50000, "emphasis": "confetti", "seconds": 10, "sound": "fanfare"}, {"min": 10000.0}], [])
    assert [tier["min"] for tier in tiers] == [50000, 10000, 0]
    assert tiers[0] == {"min": 50000, "image": "", "emphasis": "confetti", "seconds": 10, "sound": "fanfare"}
    assert tiers[2] == {"min": 0, "image": "", "emphasis": "none", "seconds": 0, "sound": ""}


def test_damaged_file_keeps_good_values():
    settings.save_data(alerts.DATA, {"layout": "zigzag", "seconds": 8, "title": "{name} 고마워요", "tiers": "x", "images": [{"id": "../x", "ext": "png"}]})
    config = alerts.load()
    assert config["layout"] == "card" and config["seconds"] == 8 and config["title"] == "{name} 고마워요"
    assert config["tiers"] == [] and config["images"] == []


def test_config_image_and_feed_routes(port):
    status, _, body = request(port, "GET", "/alerts/config")
    info = json.loads(body)
    assert status == 200 and info["layout"] == "card" and info["choices"]["layouts"]["banner"] == "가로 띠"

    status, _, body = request(port, "POST", "/alerts/image", {"name": "고양이.png", "data": base64.b64encode(PNG).decode()})
    image_id = json.loads(body)["uploaded"]
    assert status == 200 and json.loads(body)["images"] == [{"id": image_id, "ext": "png", "name": "고양이.png"}]
    status, kind, body = request(port, "GET", f"/alerts/image?id={image_id}")
    assert status == 200 and kind == "image/png" and body == PNG
    status, _, body = request(port, "POST", "/alerts/image", {"name": "글꼴", "data": base64.b64encode(b"wOF2" + bytes(8)).decode()})
    assert status == 400 and "PNG, GIF, WebP, JPEG" in json.loads(body)["error"]

    tiers = [{"min": 0}, {"min": 10000, "image": image_id, "emphasis": "confetti"}]
    status, _, body = request(port, "POST", "/alerts/config", {"layout": "side", "position": "bottom-left", "seconds": 4, "tiers": tiers,
                                                               "member_image": image_id})
    saved = json.loads(body)
    assert status == 200 and saved["layout"] == "side" and saved["tiers"][0]["image"] == image_id and saved["member_image"] == image_id
    status, _, body = request(port, "POST", "/alerts/config", {"position": "middle"})
    assert status == 400 and "위치는" in json.loads(body)["error"]
    assert alerts.load()["position"] == "bottom-left"  # 틀린 요청은 저장하지 않음

    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", "/live?feeds=alerts")
    stream = conn.getresponse()
    assert stream.fp.readline().decode().strip() == "event: alerts"
    value = json.loads(stream.fp.readline().decode().removeprefix("data: "))
    assert value["seq"] >= 2 and value["layout"] == "side" and value["tiers"][0]["emphasis"] == "confetti"
    stream.close()
    conn.close()

    # 그림을 지우면 그 그림을 쓰던 구간과 구독 그림도 비움
    status, _, body = request(port, "POST", "/alerts/image/remove", {"id": image_id})
    saved = json.loads(body)
    assert status == 200 and saved["images"] == [] and saved["member_image"] == "" and saved["tiers"][0]["image"] == ""
    assert request(port, "GET", f"/alerts/image?id={image_id}")[0] == 404
    assert not list(alerts.folder().glob("*"))


def test_control_and_overlay_pages(port):
    status, _, page = request(port, "GET", "/alerts/control")
    page = page.decode()
    assert status == 200 and "/alerts/config" in page and "/alerts/image" in page and "/alerts?preview=1" in page
    script = (STATIC / "overlay.js").read_text(encoding="utf-8")
    assert "function startAlerts" in script and "function renderAlert" in script and '"별풍선": 100' in script
    assert 'subscribe(["events", "theme", "alerts"]' in script
    css = (STATIC / "overlay.css").read_text(encoding="utf-8")
    for layout in ("banner", "bubble", "big", "side"):
        assert f".alert.layout-{layout}" in css, layout
    for enter in alerts.theme.ENTERS:  # 방송 스타일의 등장 움직임마다 알림에서 직접 고를 때의 규칙
        assert f'data-enter="{enter}"' in css and f"@keyframes alert-{'rise' if enter in ('steps', 'fade') else 'twinkle-in' if enter == 'twinkle' else enter}" in css, enter
    assert '"/alerts/control"' in (STATIC / "ui.js").read_text(encoding="utf-8")
