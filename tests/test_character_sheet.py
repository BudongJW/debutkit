"""캐릭터 그림 만들기(overlay/character_sheet.py): VRM 목록, 그린 PNG로 PNGTuber 등록, 사용 조건 승계, 잘못된 요청."""

import base64
import http.client
import json
import struct
import zlib
from pathlib import Path

import pytest

from debutkit import character, settings
from debutkit.overlay import character_sheet
from debutkit.overlay.server import OverlayServer

STATIC = Path(__file__).resolve().parent.parent / "src" / "debutkit" / "overlay" / "static"


def png(width=4, height=4):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\xff\x4f\x8b\x80" * width for _ in range(height))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def data_url(body=None):
    return "data:image/png;base64," + base64.b64encode(body or png()).decode()


def fake_vrm(name="시험 VRM"):
    """보관함에 VRM 캐릭터 정보만 적어 둔다(그리기는 브라우저 몫이라 모델 파일은 필요 없음)."""
    folder = character.library_dir() / "test-vrm"
    folder.mkdir(parents=True)
    made = character.Character("test-vrm", name, "vrm", {"model": "model.vrm"}, author="작가", version="1.0",
                               license=["상업 이용: 개인만", "수정: 허용"], warnings=["원본 확인"])
    (folder / "character.json").write_text(json.dumps(made.to_dict(), ensure_ascii=False), encoding="utf-8")
    return made


@pytest.fixture
def server():
    srv = OverlayServer([], port=0).start()
    yield srv
    srv.stop()


def request(srv, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=10)
    conn.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response.status, data


def test_list_and_register_pngtuber_from_vrm(server):
    status, body = request(server, "GET", "/character/sheet/list")
    assert status == 200 and [item["id"] for item in json.loads(body)["characters"]] == ["debutkit-3d"]  # 2D 데비는 그릴 수 없고 3D 데비는 바로
    fake_vrm()
    listed = json.loads(request(server, "GET", "/character/sheet/list")[1])["characters"]
    assert [item["id"] for item in listed] == ["debutkit-3d", "test-vrm"]

    images = {state: data_url() for state in character.PNG_STATES}
    status, body = request(server, "POST", "/character/pngtuber", {"source": "test-vrm", "name": "  내   캐릭터 ", "images": images})
    made = json.loads(body)
    assert status == 200 and made["name"] == "내 캐릭터"
    saved = character.get(made["id"])
    assert saved.kind == "png" and set(saved.files) == set(character.PNG_STATES) and saved.author == "작가"
    # 원본의 사용 조건과 경고를 그대로 옮김(완화하지 않음)
    assert saved.license[0].startswith("원본 3D 캐릭터(시험 VRM)") and "상업 이용: 개인만" in saved.license
    assert any("원본 3D 캐릭터(시험 VRM)를 그린 그림" in line for line in saved.warnings) and "원본 확인" in saved.warnings
    assert (character.library_dir() / saved.id / "talk_blink.png").read_bytes() == png()


@pytest.mark.parametrize("body, message", [
    ({"source": "debutkit", "images": {}}, "VRM 캐릭터"),
    ({"source": "test-vrm", "images": {"idle": "x"}}, "입 벌린 그림"),
    ({"source": "test-vrm", "images": {"idle": "data:image/jpeg;base64,AAAA", "talk": "data:image/jpeg;base64,AAAA"}}, "PNG 그림만"),
    ({"source": "test-vrm", "images": {"idle": "data:image/png;base64,***", "talk": "data:image/png;base64,***"}}, "올바르지 않음"),
    ({"source": "test-vrm", "images": {"idle": data_url(b"GIF89a" + bytes(40)), "talk": data_url(b"GIF89a" + bytes(40))}}, "PNG 이미지가 아님"),
])
def test_bad_requests_are_explained(server, body, message):
    fake_vrm()
    status, data = request(server, "POST", "/character/pngtuber", body)
    assert status == 400 and message in json.loads(data)["error"]
    assert [item.kind for item in character.all_characters()] == ["png", "vrm", "vrm"]  # 실패하면 아무것도 남기지 않음


def test_sheet_page_draws_locally():
    page = (STATIC / "character-sheet.html").read_text(encoding="utf-8")
    script = (STATIC / "character-sheet.js").read_text(encoding="utf-8")
    assert '/character/sheet.js' in page and "importmap" in page
    for name in ("neutral", "happy", "angry", "sad", "relaxed", "aa", "blink"):
        assert f'"{name}"' in script, name
    assert "VRMLoaderPlugin" in script and "/character/pngtuber" in script and "innerHTML" not in script
    assert "https://" not in script  # 모델과 그림은 이 PC 서버에서만


POSE = {"name": "  손   인사 ", "parts": {"body": "turn", "leftArm": "wave"}, "tweaks": {"head": [0, 0.2, -0.1], "rightHand": [0.5, 0, 0]},
        "file": {"leftUpperArm": [0, 0, 0.3826834, 0.9238795], "hips": [0, 0, 0, 1]}}


def test_saved_poses_round_trip(server):
    """내 자세: 이름으로 저장(같은 이름은 바꿈), 최근 저장 순 목록, 지우기. 설정 폴더의 poses.json에 뼈 회전 값만."""
    assert json.loads(request(server, "GET", "/character/poses")[1]) == {"poses": [], "max": character_sheet.MAX_POSES}
    status, body = request(server, "POST", "/character/poses", POSE)
    assert status == 200 and json.loads(body) == {"saved": "손 인사", "count": 1}
    request(server, "POST", "/character/poses", {"name": "만세", "parts": {"leftArm": "up"}})
    status, body = request(server, "POST", "/character/poses", {**POSE, "tweaks": {}})  # 같은 이름은 바꾸고 맨 앞으로
    assert json.loads(body)["count"] == 2
    poses = json.loads(request(server, "GET", "/character/poses")[1])["poses"]
    assert [item["name"] for item in poses] == ["손 인사", "만세"]
    assert poses[0]["tweaks"] == {} and poses[0]["file"]["leftUpperArm"] == [0, 0, 0.38268, 0.92388] and poses[1]["file"] is None
    assert json.loads(settings.data_path("poses.json").read_text(encoding="utf-8"))["poses"][1]["parts"] == {"leftArm": "up"}
    status, body = request(server, "POST", "/character/poses/remove", {"name": "만세"})
    assert status == 200 and json.loads(body) == {"removed": "만세", "count": 1}
    status, body = request(server, "POST", "/character/poses/remove", {"name": "만세"})
    assert status == 404 and "저장한 자세에 없음" in json.loads(body)["error"]


@pytest.mark.parametrize("body, message", [
    ({"name": "   "}, "자세 이름을 입력"),
    ({"name": "가" * 31}, "30자 이하"),
    ({"name": "a", "tweaks": {"head": [4, 0, 0]}}, "올바르지 않음"),  # 관절은 ±π 안
    ({"name": "a", "tweaks": {"head": [0, 0]}}, "올바르지 않음"),
    ({"name": "a", "tweaks": {"head": [True, 0, 0]}}, "올바르지 않음"),
    ({"name": "a", "tweaks": {"../x": [0, 0, 0]}}, "올바르지 않음"),
    ({"name": "a", "file": {"hips": [0, 0, 2, 1]}}, "올바르지 않음"),  # 사원수 성분은 1 이하
    ({"name": "a", "file": {"hips": [0, 0, "0", 1]}}, "올바르지 않음"),
    ({"name": "a", "parts": {"body": 3}}, "올바르지 않음"),
    ({"name": "a", "parts": ["body"]}, "올바르지 않음"),
])
def test_saved_pose_values_are_checked(server, body, message):
    status, data = request(server, "POST", "/character/poses", body)
    assert status == 400 and message in json.loads(data)["error"]
    assert json.loads(request(server, "GET", "/character/poses")[1])["poses"] == []


def test_saved_poses_have_a_limit(server, monkeypatch):
    monkeypatch.setattr(character_sheet, "MAX_POSES", 2)
    for name in ("하나", "둘"):
        assert request(server, "POST", "/character/poses", {"name": name})[0] == 200
    status, data = request(server, "POST", "/character/poses", {"name": "셋"})
    assert status == 400 and "2개까지" in json.loads(data)["error"]
    assert request(server, "POST", "/character/poses", {"name": "하나", "parts": {"body": "turn"}})[0] == 200  # 같은 이름 바꾸기는 됨
